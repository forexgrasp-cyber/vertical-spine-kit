"""Voice Agent tests.

Tests exercise services directly without importing main.py (which pulls
shared.digital_products and fails in this env where shared is site-packages).
"""

from __future__ import annotations

from shared.rag.voice_kb import (
    ingest_services_json,
    ingest_pricing_csv,
    ingest_faq_markdown,
    query_kb,
    delete_tenant_kb,
)
from services.calls_db import (
    create_call,
    get_call_by_sid,
    update_call_status,
    record_consent,
    get_consent,
    record_recording,
    delete_recording,
    list_expired_recordings,
    list_calls,
)
from shared.gdpr.retention import purge_expired_recordings, purge_recordings_older_than
from services.voice_agent import _build_spoken_response, _tier_gate, _HAS_BILLING


def test_kb_ingest_and_query():
    """KB ingest -> query round trip works."""
    tenant = "test_tenant_kb"
    try:
        count = ingest_services_json(
            tenant,
            {"services": ["cleaning", "plumbing"], "pricing": {"cleaning": 100}},
            source_name="services.json",
        )
        assert count > 0

        csv_count = ingest_pricing_csv(
            tenant,
            "item,price\ncleaning,100\nplumbing,150",
            source_name="pricing.csv",
        )
        assert csv_count > 0

        md_count = ingest_faq_markdown(
            tenant,
            "## Hours\nMon-Fri 9-5\n## Location\n123 Main St",
            source_name="faq.md",
        )
        assert md_count > 0

        results = query_kb(tenant, "cleaning price", top_k=3)
        assert len(results) <= 3
        assert all("content" in r for r in results)
        assert all("source_name" in r for r in results)
        assert all("relevance" in r for r in results)
    finally:
        delete_tenant_kb(tenant)


def test_calls_db_crud():
    """Calls DB full CRUD."""
    call_sid = "CA_test_crud_call"
    tenant = "test_crud_tenant"

    cid = create_call(
        call_sid=call_sid,
        tenant_id=tenant,
        from_number="+15551111111",
        to_number="+15552222222",
    )
    assert cid

    call = get_call_by_sid(call_sid)
    assert call is not None
    assert call["tenant_id"] == tenant
    assert call["from_number"] == "+15551111111"

    update_call_status(
        call_sid=call_sid,
        status="completed",
        intent="book_appointment",
        confidence=0.9,
        extracted_fields={"service": "cleaning", "callback_phone": "15551111111"},
        consent_granted=True,
    )
    call = get_call_by_sid(call_sid)
    assert call["status"] == "completed"
    assert call["intent"] == "book_appointment"
    assert call["confidence"] == 0.9
    assert call["consent_granted"] is True

    record_consent(
        call_sid=call_sid,
        tenant_id=tenant,
        granted=True,
        consent_type="recording",
    )
    consent = get_consent(call_sid)
    assert consent is not None
    assert consent["granted"] is True

    record_recording(
        call_sid=call_sid,
        tenant_id=tenant,
        recording_sid="RE_test_crud",
        media_url="https://example.com/recording",
        duration_seconds=120,
    )

    delete_recording("RE_test_crud")
    expired = list_expired_recordings()
    sids = [r["recording_sid"] for r in expired]
    assert "RE_test_crud" not in sids

    calls = list_calls(tenant_id=tenant, limit=10, offset=0)
    assert len(calls) >= 1


def test_compliance_purge_structure():
    """Compliance purge returns expected structure."""
    result = purge_expired_recordings(list_expired_recordings, delete_recording)
    assert "purged" in result
    assert "ttl_days" in result
    assert "errors" in result
    assert "by_tenant" in result
    assert "ran_at" in result


def test_compliance_purge_older_than():
    """purge_recordings_older_than returns structure."""
    from services.calls_db import engine, VoiceRecordingORM
    from sqlalchemy import delete as _delete

    result = purge_recordings_older_than(
        session_factory=lambda: engine.connect(),
        recordings_table=VoiceRecordingORM.__table__,
        days=30,
    )
    assert "purged" in result
    assert "days" in result


def test_spoken_response_intents():
    """Spoken response builds correctly per intent."""
    fields = {"service": "cleaning", "datetime": "2026-03-15T14:30", "address": "123 Main", "callback_phone": "15551111111"}

    # booking
    txt = _build_spoken_response("book_appointment", fields, [], "t")
    assert "cleaning" in txt
    assert "123 Main" in txt
    assert "15551111111" in txt

    # pricing with context
    txt = _build_spoken_response(
        "pricing_query", {"service": "cleaning"}, [{"content": "$100/hour"}], "t"
    )
    assert "$100/hour" in txt

    # faq with context
    txt = _build_spoken_response(
        "faq", {}, [{"content": "We are open 9-5."}], "t"
    )
    assert "9-5" in txt

    # callback
    txt = _build_spoken_response("callback_request", {"callback_phone": "15551111111"}, [], "t")
    assert "15551111111" in txt


def test_tier_gate_dev_mode():
    """Tier gate behavior depends on shared billing availability."""
    allowed, reason = _tier_gate("any_tenant")
    if not _HAS_BILLING:
        # Dev mode: no shared billing → allow
        assert allowed is True
        assert reason is None
    else:
        # With shared billing: free tier → deny
        assert allowed is False
        assert reason is not None


def test_expired_recordings_filter():
    """list_expired_recordings only returns past-expiry recordings."""
    from services.calls_db import engine, VoiceRecordingORM
    from sqlalchemy import delete

    tenant = "test_expire_tenant"
    recording_sid = "RE_test_expire"

    # Create one expired recording directly
    from datetime import datetime, timedelta, timezone
    import uuid
    expired_at = datetime.now(timezone.utc) - timedelta(days=1)
    with engine.begin() as conn:
        conn.execute(
            VoiceRecordingORM.__table__.insert().values(
                id=str(uuid.uuid4()),
                call_sid="CA_expire",
                tenant_id=tenant,
                recording_sid=recording_sid,
                media_url="https://example.com/r",
                expires_at=expired_at,
            )
        )

    try:
        expired = list_expired_recordings()
        sids = [r["recording_sid"] for r in expired if r["tenant_id"] == tenant]
        assert recording_sid in sids
    finally:
        with engine.begin() as conn:
            conn.execute(
                delete(VoiceRecordingORM).where(
                    VoiceRecordingORM.recording_sid == recording_sid
                )
            )
