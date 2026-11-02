"""Call & consent persistence for the multi-tenant voice agent.

Tables (auto-created on import):
  voice_calls       - one row per inbound Twilio call leg
  voice_consent     - consent granted/denied per call (also mirrored to
                      ImmutableAuditLog for TCPA/GDPR immutability)
  voice_recordings  - recording metadata + S3/Twilio media URL
  voice_kb_ingest   - per-tenant KB ingest job audit log
  user_tenants      - user_id -> tenant_id ownership mapping

Storage: SQLite by default (data/voice_agent.db); DATABASE_URL override for
Postgres production. All tables carry tenant_id for row-level isolation.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    or_,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from shared.security.at_rest import AtRestEmailCrypto

_PII = AtRestEmailCrypto(store="voice_agent_calls")

# ── Immutable audit log (TCPA/GDPR consent immutability) ─────────────────
_AUDIT_LOG = None


def _audit_log():
    """Lazy singleton for the shared ImmutableAuditLog."""
    global _AUDIT_LOG
    if _AUDIT_LOG is None:
        try:  # shared may be absent in dev
            from shared.audit.immutable_audit_log import (  # type: ignore
                ImmutableAuditLog,
            )

            _AUDIT_LOG = ImmutableAuditLog()
        except Exception:  # noqa: BLE001 - degrade gracefully in dev
            _AUDIT_LOG = False
    return _AUDIT_LOG


def _audit_consent(
    call_sid: str,
    tenant_id: str,
    granted: bool,
    source: str,
) -> None:
    """Write an immutable consent audit entry (fail-closed on error)."""
    audit = _audit_log()
    if not audit:
        return
    try:
        audit.log_event(
            event_type="voice_consent",
            actor_id="system",
            tenant_id=tenant_id,
            resource_type="voice_call",
            resource_id=call_sid,
            action="consent_recorded",
            details={
                "granted": granted,
                "source": source,
            },
        )
    except Exception:  # noqa: BLE001 - never break the call for audit
        pass

_DB_URL = (
    os.environ.get("VOICE_AGENT_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or f"sqlite:///{Path(__file__).resolve().parent.parent / 'data' / 'voice_agent.db'}"
)

engine = create_engine(_DB_URL, echo=False, pool_pre_ping=True)
_Base = declarative_base()
_Session = sessionmaker(bind=engine, expire_on_commit=False)


class VoiceCallORM(_Base):
    __tablename__ = "voice_calls"

    id = Column(String(36), primary_key=True)
    call_sid = Column(String(64), nullable=False, unique=True, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    from_number = Column(String(32), nullable=False)
    to_number = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="initiated")
    direction = Column(String(16), nullable=False, default="inbound")
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    recording_url = Column(Text, nullable=True)
    recording_sid = Column(String(64), nullable=True)
    intent = Column(String(64), nullable=True)
    confidence = Column(Float, nullable=True)
    extracted_fields = Column(Text, nullable=True)  # JSON blob
    consent_granted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class VoiceConsentORM(_Base):
    __tablename__ = "voice_consent"

    id = Column(String(36), primary_key=True)
    call_sid = Column(String(64), nullable=False, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    consent_type = Column(String(32), nullable=False, default="recording")  # recording | data_processing
    granted = Column(Boolean, nullable=False, default=False)
    granted_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    revoked_at = Column(DateTime, nullable=True)
    source = Column(String(32), nullable=False, default="twilio_gather")  # twilio_gather | dashboard | api


class VoiceRecordingORM(_Base):
    __tablename__ = "voice_recordings"

    id = Column(String(36), primary_key=True)
    call_sid = Column(String(64), nullable=False, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    recording_sid = Column(String(64), nullable=False, unique=True, index=True)
    media_url = Column(Text, nullable=False)
    duration_seconds = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=True, index=True)  # 30-day TCPA/GDPR purge window


class VoiceKBIngestORM(_Base):
    __tablename__ = "voice_kb_ingest"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    source_type = Column(String(32), nullable=False)  # json | csv | markdown
    source_name = Column(String(255), nullable=False)
    chunk_count = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="pending")  # pending | done | failed
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class UserTenantORM(_Base):
    """User -> tenant ownership mapping for cross-tenant access control."""

    __tablename__ = "user_tenants"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(64), nullable=False, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    role = Column(String(32), nullable=False, default="member")  # owner | member | viewer
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class CustomerTenantORM(_Base):
    """Payment customer_id -> tenant_id mapping for post-Stripe tier activation."""

    __tablename__ = "customer_tenants"

    id = Column(String(36), primary_key=True)
    customer_id = Column(String(128), nullable=False, unique=True, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    provider = Column(String(32), nullable=False, default="stripe")  # stripe | lemonsqueezy | paypal
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


# ── auto-create tables ─────────────────────────────────────────────────
_Base.metadata.create_all(engine)


def get_session():
    return _Session()


# ── call CRUD ──────────────────────────────────────────────────────────

def create_call(
    *,
    call_sid: str,
    tenant_id: str,
    from_number: str,
    to_number: str,
) -> str:
    """Idempotent: returns existing call_id if CallSid already exists."""
    existing = session_get_call(call_sid)
    if existing:
        return existing["id"]
    call_id = str(uuid.uuid4())
    with _Session() as session:
        session.add(
            VoiceCallORM(
                id=call_id,
                call_sid=call_sid,
                tenant_id=tenant_id,
                from_number=from_number,
                to_number=to_number,
            )
        )
        session.commit()
    return call_id


def session_get_call(call_sid: str) -> dict | None:
    """Get a call by SID within a session (used by create_call idempotency)."""
    with _Session() as session:
        call = session.query(VoiceCallORM).filter(VoiceCallORM.call_sid == call_sid).first()
        if not call:
            return None
        return {
            "id": call.id,
            "call_sid": call.call_sid,
            "tenant_id": call.tenant_id,
        }


def update_call_status(
    *,
    call_sid: str,
    status: str | None = None,
    ended_at: datetime | None = None,
    duration_seconds: int | None = None,
    recording_url: str | None = None,
    recording_sid: str | None = None,
    intent: str | None = None,
    confidence: float | None = None,
    extracted_fields: dict | None = None,
    consent_granted: bool | None = None,
) -> None:
    import json

    with _Session() as session:
        call = session.query(VoiceCallORM).filter(VoiceCallORM.call_sid == call_sid).first()
        if not call:
            return
        if status is not None:
            call.status = status
        if ended_at is not None:
            call.ended_at = ended_at
        if duration_seconds is not None:
            call.duration_seconds = duration_seconds
        if recording_url is not None:
            call.recording_url = recording_url
        if recording_sid is not None:
            call.recording_sid = recording_sid
        if intent is not None:
            call.intent = intent
        if confidence is not None:
            call.confidence = confidence
        if extracted_fields is not None:
            call.extracted_fields = json.dumps(extracted_fields)
        if consent_granted is not None:
            call.consent_granted = consent_granted
        session.commit()


def get_call_by_sid(call_sid: str) -> dict | None:
    with _Session() as session:
        call = session.query(VoiceCallORM).filter(VoiceCallORM.call_sid == call_sid).first()
        if not call:
            return None
        return _call_to_dict(call)


def list_calls(
    tenant_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    with _Session() as session:
        rows = (
            session.query(VoiceCallORM)
            .filter(VoiceCallORM.tenant_id == tenant_id)
            .order_by(VoiceCallORM.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return [_call_to_dict(r) for r in rows]


def _call_to_dict(call: VoiceCallORM) -> dict:
    return {
        "id": call.id,
        "call_sid": call.call_sid,
        "tenant_id": call.tenant_id,
        "from_number": call.from_number,
        "to_number": call.to_number,
        "status": call.status,
        "direction": call.direction,
        "started_at": call.started_at.isoformat() if call.started_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        "duration_seconds": call.duration_seconds,
        "recording_url": call.recording_url,
        "recording_sid": call.recording_sid,
        "intent": call.intent,
        "confidence": call.confidence,
        "extracted_fields": call.extracted_fields,
        "consent_granted": call.consent_granted,
        "created_at": call.created_at.isoformat() if call.created_at else None,
    }


# ── consent CRUD ───────────────────────────────────────────────────────

def record_consent(
    *,
    call_sid: str,
    tenant_id: str,
    granted: bool,
    consent_type: str = "recording",
    source: str = "twilio_gather",
) -> str:
    consent_id = str(uuid.uuid4())
    with _Session() as session:
        session.add(
            VoiceConsentORM(
                id=consent_id,
                call_sid=call_sid,
                tenant_id=tenant_id,
                consent_type=consent_type,
                granted=granted,
                source=source,
            )
        )
        session.commit()
    _audit_consent(call_sid, tenant_id, granted, source)
    return consent_id


def get_consent(call_sid: str) -> dict | None:
    with _Session() as session:
        row = (
            session.query(VoiceConsentORM)
            .filter(VoiceConsentORM.call_sid == call_sid)
            .order_by(VoiceConsentORM.granted_at.desc())
            .first()
        )
        if not row:
            return None
        return {
            "id": row.id,
            "call_sid": row.call_sid,
            "tenant_id": row.tenant_id,
            "consent_type": row.consent_type,
            "granted": row.granted,
            "granted_at": row.granted_at.isoformat() if row.granted_at else None,
            "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
            "source": row.source,
        }


# ── recording CRUD ─────────────────────────────────────────────────────

def record_recording(
    *,
    call_sid: str,
    tenant_id: str,
    recording_sid: str,
    media_url: str,
    duration_seconds: int | None = None,
    ttl_days: int = 30,
) -> str:
    recording_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    with _Session() as session:
        session.add(
            VoiceRecordingORM(
                id=recording_id,
                call_sid=call_sid,
                tenant_id=tenant_id,
                recording_sid=recording_sid,
                media_url=media_url,
                duration_seconds=duration_seconds,
                expires_at=expires_at,
            )
        )
        session.commit()
    return recording_id


def list_expired_recordings() -> list[dict]:
    """Return recordings past their expires_at (for the nightly purge job)."""
    with _Session() as session:
        now = datetime.now(timezone.utc)
        rows = (
            session.query(VoiceRecordingORM)
            .filter(VoiceRecordingORM.expires_at <= now)
            .all()
        )
        return [
            {
                "id": r.id,
                "call_sid": r.call_sid,
                "tenant_id": r.tenant_id,
                "recording_sid": r.recording_sid,
                "media_url": r.media_url,
            }
            for r in rows
        ]


def delete_recording(recording_sid: str) -> None:
    with _Session() as session:
        session.query(VoiceRecordingORM).filter(
            VoiceRecordingORM.recording_sid == recording_sid
        ).delete()
        session.commit()


# ── KB ingest audit ────────────────────────────────────────────────────

def record_kb_ingest(
    *,
    tenant_id: str,
    source_type: str,
    source_name: str,
    chunk_count: int,
    status: str = "pending",
    error: str | None = None,
) -> str:
    ingest_id = str(uuid.uuid4())
    with _Session() as session:
        session.add(
            VoiceKBIngestORM(
                id=ingest_id,
                tenant_id=tenant_id,
                source_type=source_type,
                source_name=source_name,
                chunk_count=chunk_count,
                status=status,
                error=error,
            )
        )
        session.commit()
    return ingest_id


# ── tenant ownership (cross-tenant access control) ───────────────────────

def add_user_tenant(
    *,
    user_id: str,
    tenant_id: str,
    role: str = "member",
) -> str:
    """Map a user to a tenant (owner | member | viewer). Idempotent."""
    existing = get_user_tenant(user_id, tenant_id)
    if existing:
        return existing["id"]
    map_id = str(uuid.uuid4())
    with _Session() as session:
        session.add(
            UserTenantORM(
                id=map_id,
                user_id=user_id,
                tenant_id=tenant_id,
                role=role,
            )
        )
        session.commit()
    return map_id


def get_user_tenant(user_id: str, tenant_id: str) -> dict | None:
    with _Session() as session:
        row = (
            session.query(UserTenantORM)
            .filter(
                UserTenantORM.user_id == user_id,
                UserTenantORM.tenant_id == tenant_id,
            )
            .first()
        )
        if not row:
            return None
        return {
            "id": row.id,
            "user_id": row.user_id,
            "tenant_id": row.tenant_id,
            "role": row.role,
        }


def get_user_tenants(user_id: str) -> list[dict]:
    with _Session() as session:
        rows = session.query(UserTenantORM).filter(
            UserTenantORM.user_id == user_id
        ).all()
        return [
            {
                "id": row.id,
                "user_id": row.user_id,
                "tenant_id": row.tenant_id,
                "role": row.role,
            }
            for row in rows
        ]


def check_tenant_access(user_id: str, tenant_id: str) -> bool:
    """Return True if user_id has any mapping to tenant_id."""
    return get_user_tenant(user_id, tenant_id) is not None


# ── customer → tenant mapping (post-Stripe tier activation) ──────────────

def add_customer_tenant(
    *,
    customer_id: str,
    tenant_id: str,
    provider: str = "stripe",
) -> str:
    """Map a payment customer_id to a tenant_id. Idempotent."""
    existing = get_customer_tenant(customer_id)
    if existing:
        return existing["id"]
    map_id = str(uuid.uuid4())
    with _Session() as session:
        session.add(
            CustomerTenantORM(
                id=map_id,
                customer_id=customer_id,
                tenant_id=tenant_id,
                provider=provider,
            )
        )
        session.commit()
    return map_id


def get_customer_tenant(customer_id: str) -> dict | None:
    with _Session() as session:
        row = (
            session.query(CustomerTenantORM)
            .filter(CustomerTenantORM.customer_id == customer_id)
            .first()
        )
        if not row:
            return None
        return {
            "id": row.id,
            "customer_id": row.customer_id,
            "tenant_id": row.tenant_id,
            "provider": row.provider,
        }


def get_tenant_by_customer(customer_id: str) -> str | None:
    """Return the tenant_id mapped to a payment customer_id, or None."""
    row = get_customer_tenant(customer_id)
    return row["tenant_id"] if row else None


# ── GDPR erasure (voice DSAR) ──────────────────────────────────────────

def erase_call_subject(subject_identifier: str) -> dict:
    """Erase all voice data for a subject (GDPR Right to Erasure).

    Matches by call_sid, from_number, to_number, or callback_phone in
    extracted_fields. Deletes call records, consent records, and recordings.
    """
    from sqlalchemy import delete, or_

    calls_erased = 0
    recordings_erased = 0
    consent_records_erased = 0

    with _Session() as session:
        # Find matching call SIDs by subject identifier
        matching_calls = session.query(VoiceCallORM).filter(
            or_(
                VoiceCallORM.call_sid == subject_identifier,
                VoiceCallORM.from_number == subject_identifier,
                VoiceCallORM.to_number == subject_identifier,
            )
        ).all()

        call_sids = [c.call_sid for c in matching_calls]
        calls_erased = len(matching_calls)

        # Also find calls where callback_phone in extracted_fields matches
        # (need to decrypt to match - fall back to raw encrypted match)
        all_calls = session.query(VoiceCallORM).all()
        for call in all_calls:
            if call.call_sid in call_sids:
                continue
            if call.extracted_fields:
                try:
                    import json

                    fields = json.loads(call.extracted_fields)
                    cb = fields.get("callback_phone", "")
                    if cb and _PII.dec(cb) == subject_identifier:
                        if call.call_sid not in call_sids:
                            call_sids.append(call.call_sid)
                            calls_erased += 1
                except Exception:  # noqa: BLE001
                    pass

        # Delete recordings for matching calls
        for call_sid in call_sids:
            recordings = session.query(VoiceRecordingORM).filter(
                VoiceRecordingORM.call_sid == call_sid
            ).all()
            recordings_erased += len(recordings)
            for recording in recordings:
                session.delete(recording)

        # Delete consent records for matching calls
        for call_sid in call_sids:
            consents = session.query(VoiceConsentORM).filter(
                VoiceConsentORM.call_sid == call_sid
            ).all()
            consent_records_erased += len(consents)
            for consent in consents:
                session.delete(consent)

        # Delete calls
        session.query(VoiceCallORM).filter(
            VoiceCallORM.call_sid.in_(call_sids) if call_sids else VoiceCallORM.id == ""
        ).delete(synchronize_session=False)

        session.commit()

    return {
        "calls": calls_erased,
        "recordings": recordings_erased,
        "consent_records": consent_records_erased,
    }
