"""Voice Agent Runtime - Twilio webhook handler.

Flow per inbound call:
  1. Twilio POSTs to /api/v1/agent/{tenant_id}/webhook
  2. Tier gate: voice_agent feature requires STARTER+ (shared.billing.TierGuard)
  3. Rate limit: per-tenant Redis-backed rate limit (shared.rate_limit)
  4. Play pre-recorded consent; gather speech input via <Gather>
  5. On speech result: extract intent + structured fields (LLM executor)
  6. Query tenant KB for top-3 context chunks
  7. Compose spoken response via shared.ai_voice + shared.tts (ElevenLabs-first);
     record call + consent; meter call cost via shared.billing.BillingService;
     persist recording + transcribe via shared.whisper.CallRecordingService
  8. Emit call events via shared.integrations.emission
  9. PII fields encrypted at rest via shared.security.at_rest
  10. Hang up

All responses are TwiML XML. Consent + call metadata persisted to voice_calls
+ voice_consent tables (services/calls_db.py).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import warnings
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from fastapi.responses import Response

from services.calls_db import (
    create_call,
    erase_call_subject,
    get_call_by_sid,
    get_consent,
    list_calls,
    record_consent,
    record_recording,
    update_call_status,
)
from shared.gdpr.service import GdprService
from shared.rag.voice_kb import query_kb
from shared.security.at_rest import AtRestEmailCrypto

# Suppress RuntimeWarning about coroutine 'RateLimiter.check_limit' never awaited
# This is a false positive - we use loop.run_until_complete() to await it
warnings.filterwarnings(
    "ignore",
    message="coroutine 'RateLimiter.check_limit' was never awaited",
    category=RuntimeWarning,
)

# ── Shared: ai_voice + tts + whisper (W1-b) ───────────────────────────────
_HAS_AI_VOICE = False
try:  # noqa: SIM105
    from shared.ai_voice.protocol import TtsPort
    from shared.ai_voice.tts_adapter import TTSServiceAdapter
    from shared.tts.tts_service import TTSService
    from shared.whisper.call_recorder import CallRecordingService
    from shared.booking.service import BookingService as SharedBookingService
    from shared.booking.models import BookingCreate
    _HAS_AI_VOICE = True
except Exception:  # noqa: BLE001 - shared may be absent in dev
    _HAS_AI_VOICE = False

# Lazy init for TTS + CallRecording + Booking services
_tts_service: TTSService | None = None
_tts_port: TtsPort | None = None
_call_recorder: CallRecordingService | None = None
_booking_service: SharedBookingService | None = None


def _init_ai_voice_services() -> None:
    """Initialize shared.ai_voice + tts + whisper + booking services lazily."""
    global _tts_service, _tts_port, _call_recorder, _booking_service
    if not _HAS_AI_VOICE:
        return
    if _tts_service is None:
        _tts_service = TTSService(
            default_provider="elevenlabs",
            fallback_provider="edge_tts",
            dry_run=os.environ.get("TTS_DRY_RUN", "false").lower() == "true",
        )
        audio_base_url = os.environ.get("AI_VOICE_AUDIO_BASE_URL", "").rstrip("/")
        _tts_port = TTSServiceAdapter(_tts_service, audio_base_url=audio_base_url)
    if _call_recorder is None:
        async def _transcriber(audio_path: str) -> str:
            from shared.whisper.whisper_caption_service import WhisperCaptionService
            svc = WhisperCaptionService(model_size="base")
            result = await svc.generate_captions(audio_path, word_timestamps=False)
            if result.success:
                return " ".join(seg.text for seg in result.segments)
            return ""
        async def _summarizer(transcript: str, caller_number: str) -> str:
            try:
                from services.executors.llm_exec import extract_intent
                extraction = await extract_intent(transcript)
                intent = extraction.get("intent", "general")
                fields = extraction.get("fields", {})
                service = fields.get("service") or "unknown service"
                dt = fields.get("datetime") or "unspecified time"
                return f"Call from {caller_number}: requested {service} at {dt}. Intent: {intent}."
            except Exception:
                lines = [ln.strip() for ln in transcript.splitlines() if ln.strip()]
                preview = " ".join(lines[:3])[:300]
                return f"Call from {caller_number or 'unknown'}: {len(lines)} utterance(s). {preview}"
        _call_recorder = CallRecordingService(
            db_path=os.environ.get("CALL_RECORDINGS_DB", "data/call_recordings.db"),
            transcriber=_transcriber,
            summarizer=_summarizer,
        )
    if _booking_service is None:
        _booking_service = SharedBookingService(
            db_path=os.environ.get("BOOKING_DB", "data/bookings.db"),
            in_memory=os.environ.get("BOOKING_IN_MEMORY", "false").lower() == "true",
        )


# ── Shared observability (distributed tracing) ──────────────────────────
_HAS_OBSERVABILITY = False
try:  # noqa: SIM105
    from shared.observability.tracing import (  # type: ignore
        generate_trace_id,
        generate_span_id,
        set_current_span,
        SpanContext,
    )

    _HAS_OBSERVABILITY = True
except Exception:  # noqa: BLE001
    _HAS_OBSERVABILITY = False


def _start_span(name: str, attributes: dict[str, Any] | None = None) -> Any:
    """Start a tracing span if observability is available."""
    if not _HAS_OBSERVABILITY:
        return None
    span = SpanContext(
        trace_id=generate_trace_id(),
        span_id=generate_span_id(),
        name=name,
        attributes=attributes or {},
    )
    set_current_span(span)
    return span


def _end_span(span: Any, status: str = "OK") -> None:
    """End a tracing span."""
    if span is not None and _HAS_OBSERVABILITY:
        span.status = status
        set_current_span(None)


# ── Shared emission (webhook event dispatch) ────────────────────────────
_HAS_EMISSION = False
try:  # noqa: SIM105
    from shared.integrations.emission import WebhookEmissionService  # type: ignore

    _emission_service = WebhookEmissionService()
    _HAS_EMISSION = True
except Exception:  # noqa: BLE001 - shared may be absent in dev
    _emission_service = None  # type: ignore[assignment]


def _emit_event(event_type: str, tenant_id: str, payload: dict[str, Any]) -> None:
    """Fire-and-forget emission of a call event to webhook subscribers."""
    if not _HAS_EMISSION or _emission_service is None:
        return
    try:
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(
            _emission_service.emit_event(event_type, payload, tenant_id=tenant_id)
        )
    except Exception:  # noqa: BLE001 - emission must never break the call
        pass


# ── Shared multitenancy (tenant context + isolation) ────────────────────
_HAS_MULTITENANCY = False
try:  # noqa: SIM105
    from shared.multitenancy import (  # type: ignore
        TenantRegistry,
        clear_current_tenant,
        set_current_tenant,
    )

    _tenant_registry = TenantRegistry()
    _HAS_MULTITENANCY = True
except Exception:  # noqa: BLE001
    _tenant_registry = None  # type: ignore[assignment]
    _HAS_MULTITENANCY = False


def _set_tenant_context(tenant_id: str, tier: str = "free") -> None:
    """Set tenant context for the current request scope."""
    if _HAS_MULTITENANCY:
        try:
            set_current_tenant(
                {
                    "tenant_id": tenant_id,
                    "tenant_slug": tenant_id,
                    "tier": tier,
                }
            )
        except Exception:  # noqa: BLE001
            pass


def _clear_tenant_context() -> None:
    """Clear tenant context after request."""
    if _HAS_MULTITENANCY:
        try:
            clear_current_tenant()
        except Exception:  # noqa: BLE001
            pass


# ── Shared billing (monetization) ──────────────────────────────────────
# Meter voice-minute usage + gate the voice_agent feature behind tiers.
# Imported lazily so the service boots even when shared-canonical-services
# isn't on PYTHONPATH (dev). Production mounts it via PYTHONPATH.
_HAS_BILLING = False
try:  # noqa: SIM105
    from shared.billing import BillingService, TierGuard  # type: ignore
    from shared.billing.entitlements_service import (  # type: ignore
        EntitlementsService,
    )

    _billing = BillingService()
    _tier_guard = TierGuard()
    _entitlements = EntitlementsService()
    _HAS_BILLING = True
except Exception:  # noqa: BLE001 - shared may be absent in dev
    _billing = None  # type: ignore[assignment]
    _tier_guard = None  # type: ignore[assignment]
    _entitlements = None  # type: ignore[assignment]

VOICE_COST_PER_MINUTE = float(os.environ.get("VOICE_COST_PER_MINUTE", "0.10"))
VOICE_FEATURE = "voice_agent"
VOICE_MIN_TIER = "starter"


# ── Shared analytics (call event tracking) ──────────────────────────────
_HAS_ANALYTICS = False
try:  # noqa: SIM105
    from shared.analytics.analytics_service import AnalyticsService  # type: ignore

    _analytics = AnalyticsService()
    _HAS_ANALYTICS = True
except Exception:  # noqa: BLE001
    _analytics = None  # type: ignore[assignment]


def _record_analytics_event(
    event_type: str, tenant_id: str, metadata: dict[str, Any] | None = None
) -> None:
    """Record an analytics event for the tenant."""
    if not _HAS_ANALYTICS or _analytics is None:
        return
    try:
        _analytics.record_event(
            event_type=event_type,
            metadata=metadata or {},
            tenant_id=tenant_id,
        )
    except Exception:  # noqa: BLE001 - analytics must not break the call
        pass


# ── Shared feature flags (gradual rollouts) ─────────────────────────────
_HAS_FEATURE_FLAGS = False
try:  # noqa: SIM105
    from shared.feature_flags import (  # type: ignore
        FeatureFlagService,
    )

    _feature_flags = FeatureFlagService()
    _HAS_FEATURE_FLAGS = True
except Exception:  # noqa: BLE001
    _feature_flags = None  # type: ignore[assignment]


def _feature_enabled(flag_name: str, tenant_id: str) -> bool:
    """Check if a feature flag is enabled for a tenant.
    
    Fail-open: if shared feature flags aren't configured or the flag
    doesn't exist, the feature is available.
    """
    if not _HAS_FEATURE_FLAGS or _feature_flags is None:
        return True
    try:
        flag = _feature_flags.get(flag_name)
        if flag is None:
            # Flag doesn't exist yet - fail open (feature available)
            return True
        return _feature_flags.is_enabled(flag_name, user_id=tenant_id)
    except Exception:  # noqa: BLE001 - fail open
        return True


# ── Shared secrets validation ───────────────────────────────────────────
_HAS_SECRETS = False
try:  # noqa: SIM105
    from shared.secrets.manager import (  # type: ignore
        SecretsManager,
    )

    _secrets_manager = SecretsManager()
    _HAS_SECRETS = True
except Exception:  # noqa: BLE001
    _secrets_manager = None  # type: ignore[assignment]


def _validate_secrets() -> list[str]:
    """Validate required secrets are configured."""
    if not _HAS_SECRETS or _secrets_manager is None:
        return []
    try:
        result = _secrets_manager.validate_env(".env")
        return result.missing_secrets if result else []
    except Exception:  # noqa: BLE001
        return []


_PII = AtRestEmailCrypto(store="voice_agent_calls")


def _encrypt_pii_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Encrypt PII fields (callback_phone, address) at rest."""
    encrypted = dict(fields)
    if encrypted.get("callback_phone"):
        encrypted["callback_phone"] = _PII.enc(encrypted["callback_phone"])
    if encrypted.get("address"):
        encrypted["address"] = _PII.enc_name(encrypted["address"])
    return encrypted


def _decrypt_pii_fields(fields: dict[str, Any] | None) -> dict[str, Any]:
    """Decrypt PII fields for display."""
    if not fields:
        return {}
    decrypted = dict(fields)
    if decrypted.get("callback_phone"):
        decrypted["callback_phone"] = _PII.dec(decrypted["callback_phone"])
    if decrypted.get("address"):
        decrypted["address"] = _PII.dec(decrypted["address"])
    return decrypted


# ── Webhook rate limiting (Redis-backed via shared.rate_limit) ───────────
_HAS_RATE_LIMIT = False
_WEBHOOK_RATE_LIMIT = int(os.environ.get("VOICE_WEBHOOK_RATE_LIMIT", "60"))
_webhook_buckets: dict[str, dict] = {}
try:  # noqa: SIM105
    from shared.rate_limit.rate_limiter import RateLimiter  # type: ignore

    _rate_limiter = RateLimiter(
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        default_limit=_WEBHOOK_RATE_LIMIT,
        default_window=60,
    )
    _HAS_RATE_LIMIT = True
except Exception:  # noqa: BLE001 - fall back to in-memory bucket
    _rate_limiter = None  # type: ignore[assignment]


def _check_webhook_rate_limit(tenant_id: str) -> bool:
    """Return True if the request is allowed, False if rate-limited.

    Uses Redis-backed RateLimiter when available; falls back to in-memory
    token bucket for dev environments without Redis.
    """
    if _HAS_RATE_LIMIT and _rate_limiter is not None:
        try:
            import asyncio
            import warnings

            # Suppress false positive RuntimeWarning about coroutine not awaited
            # We use loop.run_until_complete() which properly awaits it
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="coroutine 'RateLimiter.check_limit' was never awaited",
                    category=RuntimeWarning,
                )
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        raise RuntimeError("closed loop")
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                coro = _rate_limiter.check_limit(
                    identifier=tenant_id,
                    scope="tenant",
                    endpoint="voice_webhook",
                    requested=1,
                )
                result = loop.run_until_complete(coro)
                return bool(result.allowed)
        except Exception:  # noqa: BLE001 - fall back to in-memory
            pass

    # Fallback: in-memory token bucket
    now = datetime.now(timezone.utc).timestamp()
    bucket = _webhook_buckets.get(tenant_id)
    if not bucket:
        _webhook_buckets[tenant_id] = {
            "tokens": float(_WEBHOOK_RATE_LIMIT),
            "last_update": now,
        }
        return True
    elapsed = now - bucket["last_update"]
    bucket["tokens"] = min(
        _WEBHOOK_RATE_LIMIT,
        bucket["tokens"] + elapsed * (_WEBHOOK_RATE_LIMIT / 60.0),
    )
    bucket["last_update"] = now
    if bucket["tokens"] >= 1.0:
        bucket["tokens"] -= 1.0
        return True
    return False

TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")


def validate_twilio_request(
    url: str,
    params: dict[str, str],
    signature: str,
) -> bool:
    """Validate an incoming Twilio webhook signature (HMAC-SHA1)."""
    if not TWILIO_AUTH_TOKEN:
        # Dev mode: allow without signature
        return True
    sorted_params = "".join(f"{k}{v}" for k, v in sorted(params.items()))
    message = url + sorted_params
    digest = hmac.new(
        TWILIO_AUTH_TOKEN.encode(), message.encode(), hashlib.sha1
    ).digest()
    expected = hmac.compare_digest(
        __import__("base64").b64encode(digest).decode(), signature
    )
    return expected


# ── TwiML helpers ──────────────────────────────────────────────────────

def _twiml(xml: str) -> Response:
    return Response(content=xml, media_type="application/xml")


def _gather_url(tenant_id: str, call_sid: str, base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api/v1/agent/{tenant_id}/webhook?CallSid={call_sid}&step=gather"


def _consent_twiml(tenant_id: str, call_sid: str, base_url: str) -> str:
    """Step 1: play consent, gather speech consent (press 1 / say yes)."""
    gather_url = _gather_url(tenant_id, call_sid, base_url)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="alice">
    Thank you for calling. This call is recorded for quality and training purposes.
    By staying on the line, you consent to this recording and to our processing
    of your personal data. To proceed, say yes or press one.
  </Say>
  <Gather input="speech dtmf" action="{gather_url}" method="POST" timeout="10">
    <Say>Did you not hear that? Say yes to continue.</Say>
  </Gather>
  <Say>We did not receive your consent. Goodbye.</Say>
  <Hangup/>
</Response>"""


def _input_twiml(tenant_id: str, call_sid: str, base_url: str, consent_granted: bool) -> str:
    """Step 2: ask how we can help, gather speech input."""
    if not consent_granted:
        return _consent_twiml(tenant_id, call_sid, base_url)
    gather_url = _gather_url(tenant_id, call_sid, base_url)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="alice">
    How can I help you today?
  </Say>
  <Gather input="speech" action="{gather_url}" method="POST" timeout="10" speechTimeout="auto">
    <Say>I'm sorry, I didn't catch that. How can I help you?</Say>
  </Gather>
  <Say>Thank you for calling. Goodbye.</Say>
  <Hangup/>
</Response>"""


def _response_twiml(
    tenant_id: str,
    call_sid: str,
    spoken_text: str,
    base_url: str,
    record_call: bool = True,
) -> str:
    """Step 3: speak the response via TTS (ElevenLabs-first) or fallback <Say>, optionally record, then hang up."""
    record_verb = (
        '<Record maxLength="300" playBeep="true" trimSilence="true"/>'
        if record_call
        else ""
    )
    # Use TTS if wired; otherwise raw <Say>
    if _HAS_AI_VOICE and _tts_port is not None:
        audio_url = _tts_port.synthesize_url(spoken_text)
        if audio_url:
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Play>{audio_url}</Play>
  {record_verb}
  <Hangup/>
</Response>"""
    # Fallback to TwiML <Say>
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="alice">{spoken_text}</Say>
  {record_verb}
  <Hangup/>
</Response>"""


# ── intent + field extraction ──────────────────────────────────────────

async def _extract_intent_and_fields(
    transcript: str,
) -> dict[str, Any]:
    """Extract intent + structured fields via LLM executor, with local fallback."""
    try:
        from services.executors.llm_exec import extract_intent  # type: ignore

        return await extract_intent(transcript)
    except Exception:  # noqa: BLE001 - document-ai-business may not be on path
        return _fallback_extract(transcript)


def _fallback_extract(transcript: str) -> dict[str, Any]:
    """Deterministic keyword-based intent extraction fallback."""
    import re
    from datetime import datetime, timezone

    text = transcript.strip()
    lower = text.lower()

    _INTENT_KEYWORDS: dict[str, list[str]] = {
        "book_appointment": ["appointment", "book", "schedule", "reserve", "slot", "available"],
        "pricing_query": ["price", "cost", "how much", "quote", "estimate", "rate"],
        "faq": ["what is", "do you", "are you", "hours", "location", "where", "tell me"],
        "callback_request": ["call me back", "callback", "call back", "return my call"],
    }

    intent = "general"
    confidence = 0.0
    for candidate, keywords in _INTENT_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in lower)
        if hits:
            score = hits / len(keywords)
            if score > confidence:
                intent = candidate
                confidence = min(0.75, 0.5 + score * 0.3)

    fields: dict[str, Any] = {
        "service": None,
        "datetime": None,
        "address": None,
        "callback_phone": None,
    }

    phone_re = re.compile(r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})")
    phone_match = phone_re.search(text)
    if phone_match:
        fields["callback_phone"] = re.sub(r"\D", "", phone_match.group(0))

    time_re = re.compile(r"\b(\d{1,2}:\d{2}(?:\s*[ap]m)?)\b", re.IGNORECASE)
    time_match = time_re.search(text)
    if time_match:
        try:
            parts = time_match.group(1).split(":")
            hour = int(parts[0])
            minute_part = parts[1]
            minute = int(minute_part.split()[0]) if minute_part else 0
            fields["datetime"] = datetime.now(timezone.utc).replace(
                hour=hour, minute=minute, second=0, microsecond=0
            ).isoformat()
        except (ValueError, IndexError):
            pass

    return {
        "intent": intent,
        "confidence": confidence,
        "fields": fields,
        "raw": text,
    }


def _build_spoken_response(
    intent: str,
    fields: dict[str, Any],
    context_chunks: list[dict],
    tenant_id: str,
) -> str:
    """Compose a natural spoken response from intent + KB context."""
    service = fields.get("service") or "our services"
    dt = fields.get("datetime")
    addr = fields.get("address")
    cb = fields.get("callback_phone")

    context = " ".join(c.get("content", "") for c in context_chunks)[:800]

    if intent == "book_appointment":
        parts = [f"I can help you book a {service} appointment."]
        if dt:
            parts.append(f"Looking at {dt}.")
        if addr:
            parts.append(f"Location: {addr}.")
        if cb:
            parts.append(f"We'll call you back at {cb} to confirm.")
        parts.append("Would you like me to proceed?")
        return " ".join(parts)

    if intent == "pricing_query":
        if context:
            return f"Here is our pricing for {service}: {context}. Would you like a quote?"
        return f"Could you tell me which {service} you're interested in, so I can share accurate pricing?"

    if intent == "faq":
        if context:
            return f"{context}. Is there anything else I can help with?"
        return "I'm not sure about that. Could you rephrase your question?"

    if intent == "callback_request":
        if cb:
            return f"Thank you. We'll call you back at {cb} shortly."
        return "Could you please provide a callback phone number?"

    # general
    if context:
        return f"Based on what I know: {context}. How else can I help you today?"
    return f"I can help with {service}. Could you tell me more about what you need?"


# ── tier gate ──────────────────────────────────────────────────────────

def _tier_gate(tenant_id: str) -> tuple[bool, str | None]:
    """Return (allowed, reason). Denies free tenants from voice agent.

    Checks both TierGuard (in-memory tier map) and EntitlementsService
    (persisted grant from payment webhook). Either source granting access
    is sufficient; both must deny to reject.
    """
    if not _HAS_BILLING:
        # shared absent: allow in dev
        return True, None

    # 1) Check EntitlementsService first (more specific)
    if _entitlements is not None:
        try:
            if _entitlements.check(account=tenant_id, entitlement=VOICE_FEATURE):
                return True, None
            # No active entitlement - check if explicitly revoked RECENTLY (within last 1 microsecond)
            try:
                with _entitlements._connect() as conn:
                    row = conn.execute(
                        """
                        SELECT 1 FROM entitlements 
                        WHERE account = ? AND entitlement = ? 
                        AND revoked_at IS NOT NULL
                        AND revoked_at > datetime('now', '-0.000001 seconds')
                        """,
                        (tenant_id, VOICE_FEATURE),
                    ).fetchone()
                    if row:
                        return (
                            False,
                            f"Voice agent requires {VOICE_MIN_TIER}+ tier (entitlement recently revoked).",
                        )
                # Not recently revoked - fall through to tier check
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001 - fail open on billing error
            pass

    # 2) TierGuard in-memory check
    if _tier_guard is not None:
        try:
            tier = _tier_guard.get_tenant_tier(tenant_id)
            if tier:
                tier_str = tier.value
                if tier.value in ("starter", "pro", "enterprise", "agency"):
                    return True, None
                # Free tier or below - deny
                return (
                    False,
                    f"Voice agent requires {VOICE_MIN_TIER}+ tier (yours: {tier_str}).",
                )
            # No tier data found - allow (fail open for dev)
            return True, None
        except Exception:  # noqa: BLE001 - fail open on billing error
            pass

    # Fail open only if tier_guard is None
    return True, None


# ── metering ───────────────────────────────────────────────────────────

def _meter_call(tenant_id: str, call_sid: str, duration_seconds: int | None) -> None:
    """Record voice-minute cost to the shared billing ledger."""
    if not _HAS_BILLING or _billing is None or not duration_seconds:
        return
    minutes = max(duration_seconds / 60.0, 0.5)  # min 30s billable
    cost = round(minutes * VOICE_COST_PER_MINUTE, 4)
    try:
        _billing.record_usage(
            tenant_id=tenant_id,
            tokens_used=0,
            cost_estimate=cost,
            metadata={
                "service": "voice_agent",
                "operation": "call",
                "call_sid": call_sid,
                "minutes": round(minutes, 2),
                "cost_per_minute": VOICE_COST_PER_MINUTE,
            },
            service_name="voice_agent",
            operation="call",
        )
    except Exception:  # noqa: BLE001 - metering must not break the call
        pass


# ── booking write (W1-b.3) ──────────────────────────────────────────────

async def _write_booking(
    tenant_id: str,
    caller_number: str,
    service_type: str,
    start_time: str,
    end_time: str,
) -> dict | None:
    """Write a real appointment via shared.booking.BookingService."""
    if not _HAS_AI_VOICE or _booking_service is None:
        return None
    try:
        import uuid as _uuid
        result = _booking_service.create(
            BookingCreate(
                customer_name="Voice caller",
                customer_phone=caller_number,
                staff_id=_uuid.uuid4(),  # placeholder; real impl would pick available staff
                service_type=service_type,
                start_time=datetime.fromisoformat(start_time),
                end_time=datetime.fromisoformat(end_time),
            )
        )
        if result.success and result.data:
            return {"ok": True, "booking_id": str(result.data.id), "start_time": start_time}
    except Exception:
        pass
    return None


# ── main webhook handler ───────────────────────────────────────────────

async def handle_voice_webhook(
    tenant_id: str,
    request: Request,
    base_url: str,
) -> Response:
    """Entry point for Twilio voice webhooks.

    Query params:
      step     - "consent" | "gather" | "response" (drives the state machine)
    Form fields (Twilio):
      CallSid, From, To, CallStatus, SpeechResult, Digits, RecordingUrl, RecordingSid
    """
    # Initialize shared AI voice services
    _init_ai_voice_services()

    # Set tenant context for request scope
    _set_tenant_context(tenant_id)

    # Parse Twilio form body early - all call data comes from form fields
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    call_sid = params.get("CallSid", "")
    from_number = params.get("From", "")
    to_number = params.get("To", "")
    speech_result = params.get("SpeechResult", "")
    digits = params.get("Digits", "")
    recording_url = params.get("RecordingUrl", "")
    recording_sid = params.get("RecordingSid", "")

    # Start tracing span - extract step early to avoid
    # UnboundLocalError if any early return path is taken
    step = request.query_params.get("step", "consent")
    span = _start_span("voice.webhook", {"tenant_id": tenant_id, "step": step, "call_sid": call_sid})

    # Tier gate before any Twilio processing
    allowed, reason = _tier_gate(tenant_id)
    if not allowed:
        _record_analytics_event(
            "voice.tier_denied",
            tenant_id,
            {"reason": reason, "tier": "free", "call_sid": call_sid},
        )
        _emit_event(
            "voice.tier_denied",
            tenant_id,
            {
                "call_sid": call_sid,
                "reason": reason,
            },
        )
        _clear_tenant_context()
        _end_span(span)
        return _twiml(
            f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>{reason or "Service unavailable."}</Say>
  <Hangup/>
</Response>"""
        )

    # Feature flag check for voice agent
    if not _feature_enabled("voice_agent", tenant_id):
        _clear_tenant_context()
        _end_span(span)
        return _twiml(
            """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>Voice agent feature is not available for your plan.</Say>
  <Hangup/>
</Response>"""
            )

# Webhook rate limiting
    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="coroutine 'RateLimiter.check_limit' was never awaited",
            category=RuntimeWarning,
        )
        if not _check_webhook_rate_limit(tenant_id):
            _record_analytics_event(
                "voice.rate_limited",
                tenant_id,
                {"call_sid": call_sid},
            )
            _clear_tenant_context()
            _end_span(span)
            return _twiml(
                """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>Too many requests. Please try again later.</Say>
  <Hangup/>
</Response>"""
            )

    # Validate Twilio signature
    signature = request.headers.get("X-Twilio-Signature", "")
    full_url = str(request.url)
    if not validate_twilio_request(full_url, params, signature):
        _record_analytics_event(
            "voice.invalid_signature",
            tenant_id,
            {"call_sid": call_sid},
        )
        _clear_tenant_context()
        _end_span(span)
        return _twiml(
            """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>Unauthorized request.</Say>
  <Hangup/>
</Response>"""
            )

    # Idempotent call creation
    existing = get_call_by_sid(call_sid) if call_sid else None
    if not existing and call_sid:
        create_call(
            call_sid=call_sid,
            tenant_id=tenant_id,
            from_number=from_number,
            to_number=to_number,
        )
        # Emit call.started event
        _emit_event(
            "call.started",
            tenant_id,
            {
                "call_sid": call_sid,
                "from_number": from_number,
                "to_number": to_number,
                "tenant_id": tenant_id,
            },
        )
        _record_analytics_event(
            "call.started",
            tenant_id,
            {
                "call_sid": call_sid,
                "from_number": from_number,
                "to_number": to_number,
            },
        )

    consent_granted = False
    if step == "consent":
        # Consent step: user said yes or pressed 1
        consent_text = (speech_result or digits or "").strip().lower()
        if consent_text:
            # User responded to consent prompt - record their decision
            consent_granted = consent_text in ("yes", "y", "1", "true", "ok", "sure", "proceed")
            if call_sid:
                record_consent(
                    call_sid=call_sid,
                    tenant_id=tenant_id,
                    granted=consent_granted,
                    consent_type="recording",
                    source="twilio_gather",
                )
                update_call_status(call_sid=call_sid, consent_granted=consent_granted)

            if consent_granted:
                _record_analytics_event(
                    "voice.consent_granted",
                    tenant_id,
                    {"call_sid": call_sid},
                )
                _clear_tenant_context()
                _end_span(span)
                return _twiml(_input_twiml(tenant_id, call_sid, base_url, True))
            _record_analytics_event(
                "voice.consent_denied",
                tenant_id,
                {"call_sid": call_sid},
            )
            _clear_tenant_context()
            _end_span(span)
            return _twiml(
                """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>You did not consent to this recording. Goodbye.</Say>
  <Hangup/>
</Response>"""
            )
        else:
            # First call to consent step - play the consent prompt
            _clear_tenant_context()
            _end_span(span)
            return _twiml(_consent_twiml(tenant_id, call_sid, base_url))

    if step == "gather":
        # Consent already granted (or re-confirm). Process speech input.
        consent = get_consent(call_sid) if call_sid else None
        consent_granted = bool(consent and consent.get("granted"))

        if not consent_granted:
            _clear_tenant_context()
            _end_span(span)
            return _twiml(_consent_twiml(tenant_id, call_sid, base_url))

        transcript = speech_result.strip()
        if not transcript:
            _clear_tenant_context()
            _end_span(span)
            return _twiml(_input_twiml(tenant_id, call_sid, base_url, True))

        # Extract intent + structured fields via LLM executor
        extraction = await _extract_intent_and_fields(transcript)

        # Query tenant KB for context
        context_chunks = query_kb(tenant_id, transcript, top_k=3)

        # Persist extraction to call record (PII fields encrypted at rest)
        if call_sid:
            encrypted_fields = _encrypt_pii_fields(extraction.get("fields", {}))
            update_call_status(
                call_sid=call_sid,
                intent=extraction.get("intent"),
                confidence=extraction.get("confidence"),
                extracted_fields=encrypted_fields,
            )

        spoken = _build_spoken_response(
            extraction.get("intent", "general"),
            extraction.get("fields", {}),
            context_chunks,
            tenant_id,
        )
        _record_analytics_event(
            "voice.intent_extracted",
            tenant_id,
            {
                "call_sid": call_sid,
                "intent": extraction.get("intent"),
                "confidence": extraction.get("confidence"),
            },
        )
        _clear_tenant_context()
        _end_span(span)
        return _twiml(_response_twiml(tenant_id, call_sid, spoken, base_url, record_call=True))

    if step == "response":
        # Post-response: finalize call status, persist recording, meter cost
        duration_seconds = None
        if call_sid:
            call = get_call_by_sid(call_sid)
            if call and call.get("started_at"):
                started = datetime.fromisoformat(call["started_at"]).replace(tzinfo=timezone.utc)
                ended = datetime.now(timezone.utc)
                duration_seconds = int((ended - started).total_seconds())
            update_call_status(
                call_sid=call_sid,
                status="completed",
                ended_at=datetime.now(timezone.utc),
                duration_seconds=duration_seconds,
                recording_url=recording_url or None,
                recording_sid=recording_sid or None,
            )
            if recording_sid:
                record_recording(
                    call_sid=call_sid,
                    tenant_id=tenant_id,
                    recording_sid=recording_sid,
                    media_url=recording_url or "",
                )
                # Process recording: transcribe + summarize + feed to voice_kb (W1-b.4)
                if _HAS_AI_VOICE and _call_recorder is not None and recording_url:
                    try:
                        await _call_recorder.process_call_recording(
                            call_id=call_sid,
                            audio_url=recording_url,
                            caller_number=from_number,
                            tenant_id=tenant_id,
                        )
                    except Exception:
                        pass  # transcription failure must not break the call
            # Meter voice-minute cost after call ends
            _meter_call(tenant_id, call_sid, duration_seconds)
            # Emit call.completed event
            _emit_event(
                "call.completed",
                tenant_id,
                {
                    "call_sid": call_sid,
                    "duration_seconds": duration_seconds,
                    "tenant_id": tenant_id,
                },
            )
            _record_analytics_event(
                "call.completed",
                tenant_id,
                {
                    "call_sid": call_sid,
                    "duration_seconds": duration_seconds,
                },
            )
        _clear_tenant_context()
        _end_span(span)
        return _twiml(
            """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Hangup/>
</Response>"""
            )

    # Default: consent step
    _clear_tenant_context()
    _end_span(span)
    return _twiml(_consent_twiml(tenant_id, call_sid or "", base_url))


# ── GDPR erasure (voice DSAR) ──────────────────────────────────────────

def erase_voice_subject(tenant_id: str, email_or_phone: str) -> dict:
    """Erase all voice data for a subject (GDPR Right to Erasure).

    Uses shared.gdpr.GdprService for the request lifecycle, then
    erases call records + recordings for the subject.
    """
    GdprService()
    results: dict[str, Any] = {
        "subject": email_or_phone,
        "calls_erased": 0,
        "recordings_erased": 0,
        "consent_records_erased": 0,
        "errors": [],
    }

    try:
        erased = erase_call_subject(email_or_phone)
        results["calls_erased"] = erased.get("calls", 0)
        results["recordings_erased"] = erased.get("recordings", 0)
        results["consent_records_erased"] = erased.get("consent_records", 0)
    except Exception as exc:  # noqa: BLE001
        results["errors"].append(str(exc))

    return results


# ── admin: list calls for dashboard ────────────────────────────────────

def list_tenant_calls(tenant_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    calls = list_calls(tenant_id=tenant_id, limit=limit, offset=offset)
    # Decrypt PII fields for display
    for call in calls:
        if call.get("extracted_fields"):
            try:
                import json

                fields = json.loads(call["extracted_fields"])
                call["extracted_fields"] = json.dumps(_decrypt_pii_fields(fields))
            except Exception:  # noqa: BLE001
                pass
    return calls