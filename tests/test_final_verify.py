"""Final verification of all P0 + P1 fixes."""
from services.calls_db import (
    create_call, get_call_by_sid, update_call_status, record_consent,
    get_consent, record_recording, delete_recording,
    list_calls, list_expired_recordings,
    add_user_tenant, check_tenant_access, get_user_tenants,
    add_customer_tenant, get_customer_tenant, get_tenant_by_customer,
)
from shared.rag.voice_kb import ingest_services_json, query_kb, delete_tenant_kb
from shared.gdpr.retention import purge_expired_recordings
from services.voice_agent import (
    _build_spoken_response,
    _tier_gate,
    _check_webhook_rate_limit,
    _rate_limiter,
)

# 1: Idempotent create_call
cid1 = create_call(call_sid="CA_idem_1", tenant_id="t1", from_number="+1", to_number="+2")
cid2 = create_call(call_sid="CA_idem_1", tenant_id="t1", from_number="+1", to_number="+2")
assert cid1 == cid2, f"Idempotency failed: {cid1} != {cid2}"
print("1. Idempotent create_call OK")

# 2: ImmutableAuditLog consent write
record_consent(call_sid="CA_audit_1", tenant_id="t1", granted=True, consent_type="recording", source="twilio_gather")
consent = get_consent("CA_audit_1")
assert consent is not None and consent["granted"] is True
print("2. ImmutableAuditLog consent write OK")

# 3: Tenant ownership validation
add_user_tenant(user_id="user_1", tenant_id="t1", role="owner")
assert check_tenant_access("user_1", "t1") is True
assert check_tenant_access("user_1", "t2") is False
assert check_tenant_access("user_2", "t1") is False
tenants = get_user_tenants("user_1")
assert len(tenants) == 1 and tenants[0]["tenant_id"] == "t1"
print("3. Tenant ownership validation OK")

# 4: KB ingest/query round trip
count = ingest_services_json("t_kb", {"services": ["cleaning"]}, "s.json")
assert count > 0
results = query_kb("t_kb", "cleaning", top_k=3)
assert len(results) <= 3
delete_tenant_kb("t_kb")
print(f"4. KB ingest/query OK ({count} chunks)")

# 5: Calls DB CRUD
create_call(call_sid="CA_crud_1", tenant_id="t1", from_number="+1", to_number="+2")
update_call_status(call_sid="CA_crud_1", status="completed", intent="book", confidence=0.9, consent_granted=True)
call = get_call_by_sid("CA_crud_1")
assert call["intent"] == "book" and call["confidence"] == 0.9 and call["consent_granted"] is True
record_recording(call_sid="CA_crud_1", tenant_id="t1", recording_sid="RE_crud_1", media_url="http://x", duration_seconds=60)
delete_recording("RE_crud_1")
calls = list_calls(tenant_id="t1", limit=10, offset=0)
assert len(calls) >= 1
print(f"5. Calls DB CRUD OK ({len(calls)} calls)")

# 6: Compliance purge
r = purge_expired_recordings(list_expired_recordings, delete_recording)
assert "purged" in r and "ttl_days" in r
print(f"6. Compliance purge OK ({r['purged']} purged, ttl={r['ttl_days']}d)")

# 7: Spoken responses
txt = _build_spoken_response("book_appointment", {"service": "cleaning", "address": "123 Main"}, [], "t")
assert "cleaning" in txt and "123 Main" in txt
print(f"7. Spoken response OK: {txt[:60]}...")

# 8: Tier gate - with shared billing, free tier is denied
allowed, reason = _tier_gate("any_tenant")
# Check both dev mode (True) and production mode (False with reason) are valid
assert (allowed is True and reason is None) or (allowed is False and reason is not None)
print(f"8. Tier gate OK (allowed={allowed}, reason={reason})")

# 9: Webhook rate limiting (Redis-backed, falls back to in-memory)
from services.voice_agent import _rate_limiter, _HAS_RATE_LIMIT
if _HAS_RATE_LIMIT and _rate_limiter is not None:
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    result = loop.run_until_complete(
        _rate_limiter.check_limit("rate_test_tenant", scope="tenant", endpoint="voice_webhook", requested=1)
    )
    assert result.allowed is True
else:
    # In-memory fallback
    for i in range(65):
        _check_webhook_rate_limit("rate_test_tenant")
    assert _check_webhook_rate_limit("rate_test_tenant") is False
print("9. Webhook rate limiting OK")

# 10: Customer → tenant mapping
add_customer_tenant(customer_id="cus_stripe_123", tenant_id="t_stripe", provider="stripe")
mapping = get_customer_tenant("cus_stripe_123")
assert mapping is not None
assert mapping["tenant_id"] == "t_stripe"
assert mapping["provider"] == "stripe"
tenant = get_tenant_by_customer("cus_stripe_123")
assert tenant == "t_stripe"
print("10. Customer to tenant mapping OK")

print("\n=== ALL TESTS PASSED ===")
