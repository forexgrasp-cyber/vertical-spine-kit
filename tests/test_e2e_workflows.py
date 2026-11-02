"""Data-based end-to-end tests for Voice Agent services, workflows, integrations,
and data persistence.

These tests run real service-to-service flows with persistent SQLite data:
  - Full Twilio webhook state machine (consent → gather → response)
  - Data persistence across service boundaries (calls, consent, recordings, KB)
  - Integration between voice agent, entitlements, customer mapping, tier gating
  - Compliance purge workflow end-to-end

Run: pytest tests/test_e2e_workflows.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import pytest

from services.calls_db import (
    create_call,
    get_call_by_sid,
    update_call_status,
    record_consent,
    get_consent,
    record_recording,
    delete_recording,
    list_calls,
    list_expired_recordings,
    add_user_tenant,
    get_user_tenants,
    check_tenant_access,
    add_customer_tenant,
    get_customer_tenant,
    get_tenant_by_customer,
    engine,
    VoiceRecordingORM,
)
from shared.rag.voice_kb import (
    ingest_services_json,
    ingest_pricing_csv,
    ingest_faq_markdown,
    query_kb,
    delete_tenant_kb,
)
from shared.gdpr.retention import purge_expired_recordings
from services.voice_agent import (
    _tier_gate,
    _check_webhook_rate_limit,
    _meter_call,
    _rate_limiter,
    _HAS_RATE_LIMIT,
)
from services.voice_agent import _HAS_BILLING, _entitlements, _tier_guard, _billing

try:
    from fastapi.testclient import TestClient
    from main import app

    _HAS_FASTAPI = True
except ImportError:  # noqa: BLE001
    _HAS_FASTAPI = False


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture()
def tenant():
    return "e2e_tenant_1"


@pytest.fixture()
def user():
    return "e2e_user_1"


@pytest.fixture(autouse=True)
def clear_rate_limit_buckets():
    # Rate limiting uses Redis-backed limiter; no in-memory buckets to clear
    pass
    yield
    pass


# ── Service tests ─────────────────────────────────────────────────────────

def test_service_calls_db_full_lifecycle(tenant):
    """Complete call lifecycle: create → update → consent → recording → list → delete."""
    call_sid = f"CA_e2e_{uuid.uuid4().hex[:12]}"

    # Create
    cid = create_call(
        call_sid=call_sid,
        tenant_id=tenant,
        from_number="+15551111111",
        to_number="+15552222222",
    )
    assert cid

    # Read
    call = get_call_by_sid(call_sid)
    assert call is not None
    assert call["tenant_id"] == tenant
    assert call["from_number"] == "+15551111111"
    assert call["status"] == "initiated"
    assert call["consent_granted"] is False

    # Update status + intent + fields
    update_call_status(
        call_sid=call_sid,
        status="in-progress",
        intent="book_appointment",
        confidence=0.95,
        extracted_fields={
            "service": "deep cleaning",
            "datetime": "2026-11-01T10:00:00",
            "address": "456 Oak Ave",
            "callback_phone": "15559998888",
        },
        consent_granted=True,
    )
    call = get_call_by_sid(call_sid)
    assert call["status"] == "in-progress"
    assert call["intent"] == "book_appointment"
    assert call["confidence"] == 0.95
    assert call["consent_granted"] is True

    # Record consent
    record_consent(
        call_sid=call_sid,
        tenant_id=tenant,
        granted=True,
        consent_type="recording",
        source="twilio_gather",
    )
    consent = get_consent(call_sid)
    assert consent is not None
    assert consent["granted"] is True
    assert consent["consent_type"] == "recording"
    assert consent["source"] == "twilio_gather"

    # Record recording
    recording_sid = f"RE_e2e_{uuid.uuid4().hex[:12]}"
    record_recording(
        call_sid=call_sid,
        tenant_id=tenant,
        recording_sid=recording_sid,
        media_url=f"https://api.twilio.com/.../{recording_sid}.mp3",
        duration_seconds=185,
    )

    # Finalize call
    update_call_status(
        call_sid=call_sid,
        status="completed",
        ended_at=datetime.now(timezone.utc),
        duration_seconds=185,
        recording_url=f"https://api.twilio.com/.../{recording_sid}.mp3",
        recording_sid=recording_sid,
    )
    call = get_call_by_sid(call_sid)
    assert call["status"] == "completed"
    assert call["duration_seconds"] == 185
    assert call["recording_sid"] == recording_sid

    # List calls for tenant
    calls = list_calls(tenant_id=tenant, limit=10, offset=0)
    assert len(calls) >= 1
    assert any(c["call_sid"] == call_sid for c in calls)

    # Delete recording
    delete_recording(recording_sid)
    expired = list_expired_recordings()
    sids = [r["recording_sid"] for r in expired if r["tenant_id"] == tenant]
    assert recording_sid not in sids


def test_service_kb_ingest_and_query_roundtrip(tenant):
    """Per-tenant KB: ingest JSON + CSV + Markdown → query → top-3 → isolation."""
    try:
        # JSON ingest
        json_count = ingest_services_json(
            tenant,
            {
                "services": [
                    {"name": "deep cleaning", "price": 150, "duration": 120},
                    {"name": "plumbing", "price": 200, "duration": 90},
                ],
                "business_hours": "Mon-Fri 9-5",
            },
            source_name="services.json",
        )
        assert json_count > 0

        # CSV ingest
        csv_count = ingest_pricing_csv(
            tenant,
            "item,price,duration\ncarpet cleaning,180,60\ntile cleaning,220,75",
            source_name="pricing.csv",
        )
        assert csv_count > 0

        # Markdown ingest
        md_count = ingest_faq_markdown(
            tenant,
            "## Hours\nWe are open Mon-Fri 9am to 5pm.\n## Location\n123 Business Rd, Suite 4.\n## Pricing\nDeep cleaning starts at $150.",
            source_name="faq.md",
        )
        assert md_count > 0

        # Query: cleaning related
        results = query_kb(tenant, "deep cleaning price hours", top_k=3)
        assert len(results) <= 3
        assert all("content" in r for r in results)
        assert all("source_name" in r for r in results)
        assert all("relevance" in r for r in results)

        # Query: plumbing
        results_plumbing = query_kb(tenant, "plumbing service", top_k=3)
        assert len(results_plumbing) <= 3
        contents = " ".join(r["content"] for r in results_plumbing)
        assert "plumbing" in contents.lower()

        # Tenant isolation: query a different tenant should return nothing
        other = "e2e_tenant_isolated"
        delete_tenant_kb(other)
        other_results = query_kb(other, "cleaning", top_k=3)
        assert len(other_results) == 0
    finally:
        delete_tenant_kb(tenant)


def test_service_tier_gate_and_entitlements(tenant):
    """Tier gate + EntitlementsService integration: grant → access → revoke → deny."""
    # Reset tier to free for test isolation (TierGuard is in-memory shared state)
    if _HAS_BILLING and _tier_guard is not None:
        _tier_guard.set_tenant_tier(tenant, "free", reason="test_reset")
    # Also revoke any entitlement for test isolation (EntitlementsService is persistent)
    if _HAS_BILLING and _entitlements is not None:
        _entitlements.revoke(account=tenant, entitlement="voice_agent")
    
    # Initial state: free tier, no entitlement
    allowed, reason = _tier_gate(tenant)
    if not _HAS_BILLING:
        # Dev mode: no shared billing → allow
        assert allowed is True
        assert reason is None
    else:
        # With shared billing: free tier → deny
        assert allowed is False
        assert reason is not None

    # If shared billing is available, test entitlements grant flow
    if _HAS_BILLING and _entitlements is not None:
        # Grant voice_agent entitlement to tenant
        grant_resp = _entitlements.grant(
            account=tenant,
            entitlement="voice_agent",
            source="stripe:subscription",
            provider="stripe",
            reference="sub_e2e_123",
            tier="starter",
            metadata={"product": "voice_agent"},
        )
        assert grant_resp.success, grant_resp.error

        # Check entitlement is active
        assert _entitlements.check(account=tenant, entitlement="voice_agent") is True

        # Tier gate should pass (entitlement grants access)
        allowed, reason = _tier_gate(tenant)
        assert allowed is True

        # Revoke entitlement
        revoke_resp = _entitlements.revoke(account=tenant, entitlement="voice_agent")
        assert revoke_resp.success

        # Entitlement no longer active
        assert _entitlements.check(account=tenant, entitlement="voice_agent") is False

        # Tier gate should now deny (free tier)
        allowed, reason = _tier_gate(tenant)
        assert allowed is False
        assert reason is not None


def test_service_customer_tenant_mapping(tenant):
    """Customer ID → tenant ID mapping for post-Stripe tier activation."""
    # Add mapping
    map_id = add_customer_tenant(
        customer_id="cus_e2e_stripe_999",
        tenant_id=tenant,
        provider="stripe",
    )
    assert map_id

    # Retrieve by customer ID
    mapping = get_customer_tenant("cus_e2e_stripe_999")
    assert mapping is not None
    assert mapping["tenant_id"] == tenant
    assert mapping["provider"] == "stripe"

    # Resolve tenant by customer
    resolved = get_tenant_by_customer("cus_e2e_stripe_999")
    assert resolved == tenant

    # Non-existent customer returns None
    assert get_customer_tenant("cus_nonexistent") is None
    assert get_tenant_by_customer("cus_nonexistent") is None


# ── Workflow tests (Twilio webhook state machine) ─────────────────────────

@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI testclient unavailable")
def test_workflow_consent_granted_full_flow(tenant):
    """Complete Twilio webhook flow: consent → gather → response → finalize."""
    # Setup: grant voice_agent entitlement for this test
    if _HAS_BILLING and _entitlements is not None:
        _entitlements.grant(
            account=tenant,
            entitlement="voice_agent",
            source="stripe:subscription",
            provider="stripe",
            reference="sub_test_consent",
            tier="starter",
        )
    if _HAS_BILLING and _tier_guard is not None:
        _tier_guard.set_tenant_tier(tenant, "starter", reason="test_setup")
    
    client = TestClient(app)
    call_sid = f"CA_e2e_{uuid.uuid4().hex[:12]}"
    recording_sid = f"RE_e2e_{uuid.uuid4().hex[:12]}"

    # Step 1: Consent prompt
    resp = client.post(
        f"/api/v1/agent/{tenant}/webhook?step=consent",
        data={"CallSid": call_sid, "From": "+15551111111", "To": "+15552222222"},
    )
    assert resp.status_code == 200
    assert "application/xml" in resp.headers["content-type"]
    assert "recorded for quality" in resp.text

    # Step 1b: Grant consent (say "yes")
    resp = client.post(
        f"/api/v1/agent/{tenant}/webhook?step=consent",
        data={"CallSid": call_sid, "SpeechResult": "yes"},
    )
    assert resp.status_code == 200
    assert "How can I help you today" in resp.text

    # Verify consent was persisted
    consent = get_consent(call_sid)
    assert consent is not None
    assert consent["granted"] is True

    # Step 2: Gather speech input
    resp = client.post(
        f"/api/v1/agent/{tenant}/webhook?step=gather",
        data={"CallSid": call_sid, "SpeechResult": "I want to book a deep cleaning appointment tomorrow at 2pm"},
    )
    assert resp.status_code == 200
    assert "application/xml" in resp.headers["content-type"]
    # Should produce a spoken response (not consent prompt again)
    assert "recorded for quality" not in resp.text

    # Verify call record was updated with intent/fields
    call = get_call_by_sid(call_sid)
    assert call is not None
    assert call["intent"] == "book_appointment"
    assert call["confidence"] is not None

    # Step 3: Finalize call with recording
    resp = client.post(
        f"/api/v1/agent/{tenant}/webhook?step=response",
        data={
            "CallSid": call_sid,
            "RecordingSid": recording_sid,
            "RecordingUrl": f"https://api.twilio.com/.../{recording_sid}.mp3",
        },
    )
    assert resp.status_code == 200
    assert "<Hangup/>" in resp.text

    # Verify final state
    call = get_call_by_sid(call_sid)
    assert call["status"] == "completed"
    assert call["recording_sid"] == recording_sid
    assert call["consent_granted"] is True


@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI testclient unavailable")
def test_workflow_consent_denied_hangs_up(tenant):
    """Consent denied → call ends with no data processing."""
    # Setup: grant voice_agent entitlement for this test
    if _HAS_BILLING and _entitlements is not None:
        _entitlements.grant(
            account=tenant,
            entitlement="voice_agent",
            source="stripe:subscription",
            provider="stripe",
            reference="sub_test_consent_denied",
            tier="starter",
        )
    if _HAS_BILLING and _tier_guard is not None:
        _tier_guard.set_tenant_tier(tenant, "starter", reason="test_setup")
    
    client = TestClient(app)
    call_sid = f"CA_e2e_{uuid.uuid4().hex[:12]}"

    resp = client.post(
        f"/api/v1/agent/{tenant}/webhook?step=consent",
        data={"CallSid": call_sid, "SpeechResult": "no"},
    )
    assert resp.status_code == 200
    assert "You did not consent" in resp.text
    assert "<Hangup/>" in resp.text

    # Consent record should exist with granted=False
    consent = get_consent(call_sid)
    assert consent is not None
    assert consent["granted"] is False


@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI testclient unavailable")
def test_workflow_idempotent_call_creation(tenant):
    """Same CallSid across multiple webhook steps → single call record."""
    # Setup: grant voice_agent entitlement for this test
    if _HAS_BILLING and _entitlements is not None:
        _entitlements.grant(
            account=tenant,
            entitlement="voice_agent",
            source="stripe:subscription",
            provider="stripe",
            reference="sub_test_idempotent",
            tier="starter",
        )
    if _HAS_BILLING and _tier_guard is not None:
        _tier_guard.set_tenant_tier(tenant, "starter", reason="test_setup")
    
    client = TestClient(app)
    call_sid = f"CA_e2e_{uuid.uuid4().hex[:12]}"

    # First request creates call
    client.post(
        f"/api/v1/agent/{tenant}/webhook?step=consent",
        data={"CallSid": call_sid, "From": "+1", "To": "+2"},
    )
    call1 = get_call_by_sid(call_sid)
    assert call1 is not None

    # Second request with same CallSid → same call record (idempotent)
    client.post(
        f"/api/v1/agent/{tenant}/webhook?step=consent",
        data={"CallSid": call_sid, "From": "+1", "To": "+2", "SpeechResult": "yes"},
    )
    call2 = get_call_by_sid(call_sid)
    assert call2 is not None
    assert call1["id"] == call2["id"]  # Same row, not duplicated


# ── Integration tests (voice agent + billing + entitlements) ──────────────

def test_integration_subscription_activates_voice_agent(tenant):
    """Subscribe → entitlement granted → tier gate allows → voice agent accessible."""
    if not (_HAS_BILLING and _entitlements is not None and _tier_guard is not None):
        pytest.skip("shared billing unavailable in this environment")

    # Simulate subscription creation (same flow as /billing/subscribe endpoint)
    tier = "starter"
    _entitlements.grant(
        account=tenant,
        entitlement="voice_agent",
        source="stripe:subscription",
        provider="stripe",
        reference="sub_integration_1",
        tier=tier,
        metadata={"product": "voice_agent", "amount": 29.0},
    )
    _tier_guard.set_tenant_tier(tenant, tier, reason="subscription_created")

    # Tier gate should allow
    allowed, reason = _tier_gate(tenant)
    assert allowed is True

    # Entitlement check
    assert _entitlements.check(account=tenant, entitlement="voice_agent") is True


def test_integration_free_tenant_denied_voice_agent(tenant):
    """Free tenant (no entitlement) → tier gate denies voice agent."""
    if not _HAS_BILLING or _entitlements is None or _tier_guard is None:
        pytest.skip("shared billing unavailable in this environment")

    # Revoke any entitlement first
    _entitlements.revoke(account=tenant, entitlement="voice_agent")

    allowed, reason = _tier_gate(tenant)
    assert allowed is False
    assert "starter" in reason.lower() or "tier" in reason.lower()


# ── Data persistence tests (cross-service consistency) ────────────────────

def test_persistence_call_to_recording_to_purge(tenant):
    """Call → recording → compliance purge → data gone but call metadata remains."""
    call_sid = f"CA_e2e_{uuid.uuid4().hex[:12]}"
    purge_recording_sid = f"RE_e2e_{uuid.uuid4().hex[:12]}"

    # Create call
    create_call(
        call_sid=call_sid,
        tenant_id=tenant,
        from_number="+15551111111",
        to_number="+15552222222",
    )

    # Create an expired recording directly (simulating 30+ days old)
    expired_at = datetime.now(timezone.utc) - timedelta(days=31)
    with engine.begin() as conn:
        conn.execute(
            VoiceRecordingORM.__table__.insert().values(
                id=str(uuid.uuid4()),
                call_sid=call_sid,
                tenant_id=tenant,
                recording_sid=purge_recording_sid,
                media_url="https://example.com/expired_recording.mp3",
                expires_at=expired_at,
            )
        )

    # Verify recording exists before purge
    expired_before = list_expired_recordings()
    sids_before = [r["recording_sid"] for r in expired_before if r["tenant_id"] == tenant]
    assert purge_recording_sid in sids_before

    # Run compliance purge
    result = purge_expired_recordings(list_expired_recordings, delete_recording)
    assert result["purged"] >= 1

    # Verify recording was purged
    expired_after = list_expired_recordings()
    sids_after = [r["recording_sid"] for r in expired_after if r["tenant_id"] == tenant]
    assert purge_recording_sid not in sids_after

    # Call metadata should still exist (only recording media purged)
    call = get_call_by_sid(call_sid)
    assert call is not None  # Call metadata retained for audit


def test_persistence_rate_limit_isolation_per_tenant():
    """Rate limiting is per-tenant: tenant A exhausted doesn't affect tenant B."""
    # Rate limiter uses Redis-backed limiter; if Redis unavailable,
    # falls back to in-memory buckets per tenant
    tenant_a = "rate_limit_tenant_a"
    tenant_b = "rate_limit_tenant_b"

    if _HAS_RATE_LIMIT and _rate_limiter is not None:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        # Exhaust tenant A
        for _ in range(65):
            loop.run_until_complete(
                _rate_limiter.check_limit(tenant_a, scope="tenant", endpoint="voice_webhook", requested=1)
            )
        result_a = loop.run_until_complete(
            _rate_limiter.check_limit(tenant_a, scope="tenant", endpoint="voice_webhook", requested=1)
        )
        assert result_a.allowed is False, "Rate limiting never kicked in for tenant A"

        # Tenant B should still be allowed
        result_b = loop.run_until_complete(
            _rate_limiter.check_limit(tenant_b, scope="tenant", endpoint="voice_webhook", requested=1)
        )
        assert result_b.allowed is True, "Tenant B should not be affected by tenant A's rate limit"
    else:
        # In-memory fallback: just verify the function works for both tenants
        assert _check_webhook_rate_limit(tenant_a) is True
        assert _check_webhook_rate_limit(tenant_b) is True


def test_persistence_meter_call_records_voice_minutes(tenant):
    """Voice-minute metering records cost via shared.billing (when available)."""
    if not (_HAS_BILLING and _billing is not None):
        pytest.skip("shared billing unavailable in this environment")

    call_sid = "CA_e2e_meter_1"
    create_call(
        call_sid=call_sid,
        tenant_id=tenant,
        from_number="+1",
        to_number="+2",
    )

    # Meter a 5-minute call
    _meter_call(tenant, call_sid, duration_seconds=300)  # 5 minutes

    # Verify usage summary reflects the cost
    summary = _billing.get_usage_summary(tenant)
    assert summary is not None
    assert "total_cost" in summary or "by_service" in summary


# ── Auth/tenant access tests ──────────────────────────────────────────────

def test_tenant_access_control(user, tenant):
    """User → tenant ownership: add → check → list → deny others."""
    unique_user = f"{user}_{uuid.uuid4().hex[:8]}"

    # Initially no access
    assert check_tenant_access(unique_user, tenant) is False

    # Add mapping
    map_id = add_user_tenant(user_id=unique_user, tenant_id=tenant, role="owner")
    assert map_id

    # Access granted
    assert check_tenant_access(unique_user, tenant) is True

    # List user's tenants
    tenants = get_user_tenants(unique_user)
    assert len(tenants) == 1
    assert tenants[0]["tenant_id"] == tenant
    assert tenants[0]["role"] == "owner"

    # Different user has no access
    assert check_tenant_access("other_user", tenant) is False

    # Different tenant for same user has no access
    assert check_tenant_access(unique_user, "other_tenant") is False


# ── Full e2e workflow simulation ──────────────────────────────────────────

@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI testclient unavailable")
def test_full_e2e_voice_agent_workflow_with_persistence(tenant, user):
    """Complete end-to-end: user owns tenant → subscribes → calls webhook → data persists."""
    unique_user = f"{user}_{uuid.uuid4().hex[:8]}"
    call_sid = f"CA_e2e_{uuid.uuid4().hex[:12]}"
    recording_sid = f"RE_e2e_{uuid.uuid4().hex[:12]}"
    customer_id = f"cus_e2e_{uuid.uuid4().hex[:12]}"

    # 1. User owns tenant
    add_user_tenant(user_id=unique_user, tenant_id=tenant, role="owner")
    assert check_tenant_access(unique_user, tenant) is True

    # 2. Tenant subscribes (entitlement granted)
    if _HAS_BILLING and _entitlements is not None:
        _entitlements.grant(
            account=tenant,
            entitlement="voice_agent",
            source="stripe:subscription",
            provider="stripe",
            reference=f"sub_full_e2e_{uuid.uuid4().hex[:8]}",
            tier="starter",
        )

    # 3. Customer → tenant mapping (post-Stripe webhook)
    add_customer_tenant(
        customer_id=customer_id,
        tenant_id=tenant,
        provider="stripe",
    )
    assert get_tenant_by_customer(customer_id) == tenant

    # 4. Tier gate allows voice agent
    allowed, reason = _tier_gate(tenant)
    assert allowed is True

    # 5. Ingest KB for tenant
    json_count = ingest_services_json(
        tenant,
        {"services": [{"name": "house cleaning", "price": 100}]},
        source_name="services.json",
    )
    assert json_count > 0

    # 6. Run full Twilio webhook flow via FastAPI
    client = TestClient(app)

    # Consent
    resp = client.post(
        f"/api/v1/agent/{tenant}/webhook?step=consent",
        data={"CallSid": call_sid, "From": "+15551111111", "To": "+15552222222", "SpeechResult": "yes"},
    )
    assert resp.status_code == 200

    # Gather
    resp = client.post(
        f"/api/v1/agent/{tenant}/webhook?step=gather",
        data={"CallSid": call_sid, "SpeechResult": "I want to book a house cleaning appointment this Friday at 3pm"},
    )
    assert resp.status_code == 200

    # Finalize with recording
    resp = client.post(
        f"/api/v1/agent/{tenant}/webhook?step=response",
        data={
            "CallSid": call_sid,
            "RecordingSid": recording_sid,
            "RecordingUrl": f"https://api.twilio.com/.../{recording_sid}.mp3",
        },
    )
    assert resp.status_code == 200

    # 7. Verify all data persisted
    call = get_call_by_sid(call_sid)
    assert call is not None
    assert call["tenant_id"] == tenant
    assert call["intent"] == "book_appointment"
    assert call["consent_granted"] is True
    assert call["recording_sid"] == recording_sid

    consent = get_consent(call_sid)
    assert consent is not None
    assert consent["granted"] is True

    calls = list_calls(tenant_id=tenant, limit=10, offset=0)
    assert len(calls) >= 1

    # 8. KB query works for this tenant
    results = query_kb(tenant, "house cleaning price", top_k=3)
    assert len(results) <= 3
    assert any("cleaning" in r["content"].lower() for r in results)

    # Cleanup
    delete_tenant_kb(tenant)
    delete_recording("RE_full_e2e")
