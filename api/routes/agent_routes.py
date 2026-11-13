"""Voice Agent API routes.

Mounted at /api/v1/agent in main.py.

Endpoints:
  POST  /agent/{tenant_id}/webhook          - Twilio voice webhook (TwiML)
  POST  /agent/{tenant_id}/kb/ingest         - Ingest tenant KB source
  GET   /agent/{tenant_id}/calls             - List tenant calls (dashboard)
  GET   /agent/{tenant_id}/calls/{call_sid}  - Get single call record
  POST  /agent/{tenant_id}/billing/checkout  - Create checkout (shared.billing)
  POST  /agent/{tenant_id}/billing/subscribe - Subscribe to voice agent plan
  GET   /agent/{tenant_id}/billing/usage     - Voice-minute usage + cost
  GET   /agent/{tenant_id}/billing/tier      - Current tier + access check
  POST  /agent/{tenant_id}/webhooks/retell/call   - Retell missed-call webhook
  POST  /agent/{tenant_id}/webhooks/vapi/call     - Vapi missed-call webhook
  POST  /agent/{tenant_id}/webhooks/bland/call    - Bland missed-call webhook
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path as PathParam, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from shared.auth import get_current_user
from services.calls_db import (
    add_customer_tenant,
    check_tenant_access,
    get_call_by_sid,
    list_calls as list_tenant_calls,
)
from services.voice_agent import handle_voice_webhook

# ── shared.missed_lead (W1-b.1) ──────────────────────────────────────────
_HAS_MISSED_LEAD = False
try:  # noqa: SIM105
    from shared.missed_lead.service import get_missed_lead_service
    from shared.missed_lead.webhooks import (
        RetellWebhookAdapter,
        VapiWebhookAdapter,
        BlandWebhookAdapter,
    )
    from shared.missed_lead.responder import WhatsAppLeadResponder
    from shared.missed_lead.trade import LOCKSMITH_PROFILE
    from shared.booking.service import BookingService as SharedBookingService
    _HAS_MISSED_LEAD = True
except Exception:  # noqa: BLE001
    _HAS_MISSED_LEAD = False

router = APIRouter(tags=["Voice Agent"])

BASE_URL = os.environ.get(
    "VOICE_AGENT_BASE_URL",
    "http://localhost:8000",
)


# ── request/response models ────────────────────────────────────────────

class KBIngestRequest(BaseModel):
    source_type: str = Field(
        ...,
        description="json | csv | markdown",
        examples=["json"],
    )
    source_name: str = Field(
        ...,
        description="Display name for the source",
        examples=["services.json"],
    )
    content: str = Field(..., description="Raw document content to ingest")


class KBIngestResponse(BaseModel):
    tenant_id: str
    source_name: str
    source_type: str
    chunk_count: int
    status: str


class CallListResponse(BaseModel):
    tenant_id: str
    calls: list[dict]
    limit: int
    offset: int


# ── shared billing (lazy import; absent in dev) ────────────────────────

_HAS_BILLING = False
try:  # noqa: SIM105
    from shared.billing import UnifiedPaymentService  # type: ignore
    from shared.billing.billing_service import (  # type: ignore
        BillingService,
        TierGuard,
    )
    from shared.billing.entitlements_service import (  # type: ignore
        EntitlementsService,
    )
    _billing = BillingService()
    _tier_guard = TierGuard()
    _payment = UnifiedPaymentService()
    _entitlements = EntitlementsService()
    _HAS_BILLING = True
except Exception:  # noqa: BLE001
    _billing = None  # type: ignore[assignment]
    _tier_guard = None  # type: ignore[assignment]
    _payment = None  # type: ignore[assignment]
    _entitlements = None  # type: ignore[assignment]


# ── auth dependency ────────────────────────────────────────────────────

async def require_auth(current_user: dict = Depends(get_current_user)):
    """Require a valid platform session for billing/admin endpoints."""
    return current_user


async def require_tenant_access(
    tenant_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Require that the authenticated user owns the requested tenant_id."""
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Authenticated user has no user_id",
        )
    if not check_tenant_access(user_id, tenant_id):
        raise HTTPException(
            status_code=403,
            detail="Tenant access denied",
        )
    return current_user


class CheckoutRequest(BaseModel):
    tier: str = Field("starter", description="starter | pro | agency")
    amount: float = Field(29.0, description="USD amount")
    currency: str = Field("usd", description="ISO currency code")
    customer_email: str = Field(..., description="Customer email")
    provider: str | None = Field(None, description="stripe | lemonsqueezy | paypal ...")
    success_url: str = Field(..., description="Post-success redirect URL")
    cancel_url: str = Field(..., description="Post-cancel redirect URL")


class CheckoutResponse(BaseModel):
    provider: str
    checkout_url: str
    amount: float
    currency: str
    session_id: str | None = None


class SubscribeRequest(BaseModel):
    tier: str = Field("starter", description="starter | pro | agency")
    amount: float = Field(29.0, description="Monthly USD amount")
    interval: str = Field("month", description="month | year")
    customer_email: str = Field(..., description="Customer email")
    provider: str | None = Field(None, description="stripe | lemonsqueezy")


class SubscribeResponse(BaseModel):
    subscription_id: str
    provider: str
    status: str
    amount: float
    interval: str


class UsageResponse(BaseModel):
    tenant_id: str
    total_calls: int
    total_minutes: float
    total_cost: float
    by_service: dict[str, dict[str, float]]


class TierResponse(BaseModel):
    tenant_id: str
    tier: str
    voice_agent_access: bool


# ── Twilio webhook ─────────────────────────────────────────────────────

@router.post("/{tenant_id}/webhook")
async def agent_webhook(
    request: Request,
    tenant_id: str = PathParam(..., description="Tenant identifier"),
):
    """Twilio voice webhook. Returns TwiML XML.

    Twilio POSTs here on every inbound call leg. The `step` query param
    drives the consent -> input -> response state machine.
    """
    return await handle_voice_webhook(
        tenant_id=tenant_id,
        request=request,
        base_url=BASE_URL,
    )


# ── KB ingest ──────────────────────────────────────────────────────────

@router.post("/{tenant_id}/kb/ingest", response_model=KBIngestResponse)
async def ingest_kb(
    tenant_id: str = PathParam(..., description="Tenant identifier"),
    payload: KBIngestRequest = Body(...),
):
    """Ingest a per-tenant knowledge-base source.

    Supported source_type values:
      - json    : services JSON (pricing, menu, service list)
      - csv     : pricing CSV (one row per chunk)
      - markdown: FAQ / policy Markdown
    """
    from shared.rag import (
        ingest_faq_markdown,
        ingest_pricing_csv,
        ingest_services_json,
    )

    if payload.source_type == "json":
        chunk_count = ingest_services_json(tenant_id, payload.content, payload.source_name)
    elif payload.source_type == "csv":
        chunk_count = ingest_pricing_csv(tenant_id, payload.content, payload.source_name)
    elif payload.source_type == "markdown":
        chunk_count = ingest_faq_markdown(tenant_id, payload.content, payload.source_name)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source_type: {payload.source_type}",
        )

    return KBIngestResponse(
        tenant_id=tenant_id,
        source_name=payload.source_name,
        source_type=payload.source_type,
        chunk_count=chunk_count,
        status="done" if chunk_count > 0 else "empty",
    )


# ── billing: checkout ──────────────────────────────────────────────────

@router.post("/{tenant_id}/billing/checkout", response_model=CheckoutResponse)
async def create_checkout(
    tenant_id: str = PathParam(..., description="Tenant identifier"),
    payload: CheckoutRequest = Body(...),
    _auth: dict = Depends(require_tenant_access),
):
    """Create a payment checkout for the voice agent plan via shared.billing.

    Falls back to a dry-run URL when no payment provider is configured.
    """
    if not _HAS_BILLING or _payment is None:
        raise HTTPException(
            status_code=503,
            detail="Billing not available: shared.canonical-services not on PYTHONPATH",
        )
    try:
        result = _payment.create_payment_link(
            product_id=f"voice-agent-{payload.tier}",
            product_name=f"Voice Agent — {payload.tier}",
            amount=payload.amount,
            currency=payload.currency,
            customer_email=payload.customer_email,
            provider=payload.provider,
            metadata={
                "tenant_id": tenant_id,
                "tier": payload.tier,
                "product": "voice_agent",
            },
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Checkout failed: {exc}") from exc

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Checkout failed")

    data = result.data or {}
    return CheckoutResponse(
        provider=data.get("provider", payload.provider or "stripe"),
        checkout_url=data.get("payment_url") or data.get("checkout_url") or "",
        amount=payload.amount,
        currency=payload.currency,
        session_id=data.get("payment_link_id") or data.get("subscription_id"),
    )


# ── billing: subscribe ─────────────────────────────────────────────────

@router.post("/{tenant_id}/billing/subscribe", response_model=SubscribeResponse)
async def create_subscription(
    tenant_id: str = PathParam(..., description="Tenant identifier"),
    payload: SubscribeRequest = Body(...),
    _auth: dict = Depends(require_tenant_access),
):
    """Create a recurring voice-agent subscription via shared.billing."""
    if not _HAS_BILLING or _payment is None:
        raise HTTPException(
            status_code=503,
            detail="Billing not available: shared.canonical-services not on PYTHONPATH",
        )
    try:
        result = _payment.create_subscription(
            product_id=f"voice-agent-{payload.tier}",
            product_name=f"Voice Agent — {payload.tier}",
            amount=payload.amount,
            billing_interval=payload.interval,
            customer_email=payload.customer_email,
            provider=payload.provider,
            metadata={"tenant_id": tenant_id, "tier": payload.tier, "product": "voice_agent"},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Subscription failed: {exc}") from exc

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Subscription failed")

    data = result.data or {}

    # Grant entitlement + set tier in TierGuard for immediate access
    if _HAS_BILLING and _entitlements is not None:
        try:
            _entitlements.grant(
                account=tenant_id,
                entitlement="voice_agent",
                source=f"{data.get('provider', 'stripe')}:subscription",
                provider=data.get("provider", "stripe"),
                reference=data.get("subscription_id", ""),
                tier=payload.tier,
                metadata={
                    "tenant_id": tenant_id,
                    "amount": payload.amount,
                    "interval": payload.interval,
                    "customer_email": payload.customer_email,
                },
            )
        except Exception:  # noqa: BLE001 - entitlement grant must not fail subscription
            pass
    if _HAS_BILLING and _tier_guard is not None:
        try:
            _tier_guard.set_tenant_tier(tenant_id, payload.tier, reason="subscription_created")
        except Exception:  # noqa: BLE001
            pass

    return SubscribeResponse(
        subscription_id=data.get("subscription_id", ""),
        provider=data.get("provider", payload.provider or "stripe"),
        status=data.get("status", "active"),
        amount=payload.amount,
        interval=payload.interval,
    )


# ── billing: usage ─────────────────────────────────────────────────────

@router.get("/{tenant_id}/billing/usage", response_model=UsageResponse)
async def get_usage(
    tenant_id: str = PathParam(..., description="Tenant identifier"),
    _auth: dict = Depends(require_tenant_access),
):
    """Voice-minute usage + cost for a tenant (shared.billing ledger)."""
    if not _HAS_BILLING or _billing is None:
        raise HTTPException(
            status_code=503,
            detail="Billing not available: shared.canonical-services not on PYTHONPATH",
        )
    try:
        summary = _billing.get_usage_summary(tenant_id)
        by_service = summary.get("by_service", {})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Usage read failed: {exc}") from exc

    total_calls = int(summary.get("total_calls", 0))
    total_cost = float(summary.get("total_cost", 0.0))
    # Derive minutes from cost at VOICE_COST_PER_MINUTE
    import os as _os
    cpm = float(_os.environ.get("VOICE_COST_PER_MINUTE", "0.10"))
    total_minutes = round(total_cost / cpm, 2) if cpm else 0.0

    return UsageResponse(
        tenant_id=tenant_id,
        total_calls=total_calls,
        total_minutes=total_minutes,
        total_cost=round(total_cost, 4),
        by_service=by_service,
    )


# ── billing: tier ──────────────────────────────────────────────────────

@router.get("/{tenant_id}/billing/tier", response_model=TierResponse)
async def get_tier(
    tenant_id: str = PathParam(..., description="Tenant identifier"),
    _auth: dict = Depends(require_tenant_access),
):
    """Current tenant tier + voice_agent feature access (shared.billing TierGuard)."""
    if not _HAS_BILLING or _tier_guard is None:
        raise HTTPException(
            status_code=503,
            detail="Billing not available: shared.canonical-services not on PYTHONPATH",
        )
    try:
        tier = _tier_guard.get_tenant_tier(tenant_id)
        access = _tier_guard.check_access(tenant_id, "voice_agent")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Tier check failed: {exc}") from exc

    return TierResponse(
        tenant_id=tenant_id,
        tier=tier.value,
        voice_agent_access=access,
    )


# ── billing: payment webhook (signature-validated, no session auth) ──────

@router.post("/{tenant_id}/billing/webhook/{provider}")
async def billing_webhook(
    tenant_id: str = PathParam(..., description="Tenant identifier"),
    provider: str = PathParam(..., description="stripe | lemonsqueezy | paypal | gumroad"),
    request: Any = None,
):
    """Receive and verify payment provider webhooks (fail-closed).

    Validated by shared.billing.UnifiedPaymentService.verify_and_handle.
    Tenant id is carried in webhook metadata; this endpoint does not
    require a platform session because providers POST directly.
    """
    if not _HAS_BILLING or _payment is None:
        raise HTTPException(
            status_code=503,
            detail="Billing not available: shared.canonical-services not on PYTHONPATH",
        )

    body = await request.body()
    headers = dict(request.headers)

    try:
        result = _payment.verify_and_handle(
            raw_payload=body,
            headers=headers,
            provider=provider,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Webhook handling failed: {exc}") from exc

    if not result.success:
        return PlainTextResponse(
            content=result.error or "Webhook rejected",
            status_code=400,
        )

    data = result.data or {}

    # Map payment customer_id → tenant_id for post-Stripe tier activation
    customer_id = (
        data.get("customer_id")
        or data.get("customer")
        or (data.get("metadata") or {}).get("customer_id")
    )
    webhook_tenant_id = (data.get("metadata") or {}).get("tenant_id") or tenant_id
    if _HAS_BILLING and customer_id and _entitlements is not None:
        try:
            add_customer_tenant(
                customer_id=str(customer_id),
                tenant_id=str(webhook_tenant_id),
                provider=provider,
            )
        except Exception:  # noqa: BLE001 - customer mapping must not fail webhook
            pass

    # Grant entitlement on subscription activation
    if _HAS_BILLING and _entitlements is not None:
        event_type = str(data.get("event_type", ""))
        if "subscription" in event_type or "checkout" in event_type or "invoice" in event_type:
            try:
                _entitlements.grant(
                    account=str(webhook_tenant_id),
                    entitlement="voice_agent",
                    source=f"{provider}:webhook",
                    provider=provider,
                    reference=str(data.get("subscription_id") or data.get("payment_id") or ""),
                    tier=str((data.get("metadata") or {}).get("tier", "starter")),
                    metadata={
                        "tenant_id": webhook_tenant_id,
                        "provider": provider,
                        "event_type": event_type,
                    },
                )
                if _tier_guard is not None:
                    _tier_guard.set_tenant_tier(
                        str(webhook_tenant_id),
                        str((data.get("metadata") or {}).get("tier", "starter")),
                        reason="payment_webhook",
                    )
            except Exception:  # noqa: BLE001 - entitlement grant must not fail webhook
                pass

    return {"status": "ok", "provider": provider, "data": result.data}


# ── Missed-lead webhooks (W1-b.1) ──────────────────────────────────────

# Per-tenant MissedLeadService cache (wired with shared.booking for real writes)
_missed_lead_services: dict[str, Any] = {}


def _get_missed_lead_service(tenant_id: str) -> Any | None:
    """Get or create a MissedLeadService for a tenant, wired with BookingService and WhatsApp responder."""
    if not _HAS_MISSED_LEAD:
        return None
    if tenant_id in _missed_lead_services:
        return _missed_lead_services[tenant_id]
    # Wire BookingService for real appointment writes (W1-b.3)
    booking_svc = SharedBookingService(
        db_path=os.environ.get("BOOKING_DB", "data/bookings.db"),
        tenant_id=tenant_id,
        in_memory=os.environ.get("BOOKING_IN_MEMORY", "false").lower() == "true",
    )
    # Wire WhatsApp responder for auto-recovery messages (W1-b.1 WhatsApp recovery)
    whatsapp_responder = None
    if os.environ.get("WHATSAPP_PHONE_NUMBER_ID") and os.environ.get("WHATSAPP_ACCESS_TOKEN"):
        try:
            whatsapp_responder = WhatsAppLeadResponder.from_env(
                tenant_id=tenant_id,
                dry_run=os.environ.get("MISSED_LEAD_DRY_RUN", "false").lower() == "true",
            )
        except Exception:  # noqa: BLE001 - responder optional
            whatsapp_responder = None
    svc = get_missed_lead_service(
        tenant_id=tenant_id,
        profile=LOCKSMITH_PROFILE,
        booking_service=booking_svc,
        responder=whatsapp_responder,
        dry_run=os.environ.get("MISSED_LEAD_DRY_RUN", "false").lower() == "true",
    )
    _missed_lead_services[tenant_id] = svc
    return svc


# Dynamic per-tenant missed-call webhook endpoints
# These accept provider webhooks and route to the tenant's MissedLeadService

class MissedCallWebhookRequest(BaseModel):
    """Generic request model for provider webhook payloads."""
    pass


@router.post("/{tenant_id}/webhooks/retell/call")
async def retell_missed_call_webhook(
    tenant_id: str = PathParam(..., description="Tenant identifier"),
    payload: dict[str, Any] = Body(...),
):
    """Retell.ai missed-call webhook. Feeds shared.missed_lead recovery flow."""
    if not _HAS_MISSED_LEAD:
        raise HTTPException(status_code=503, detail="Missed-lead service not available")
    svc = _get_missed_lead_service(tenant_id)
    if svc is None:
        raise HTTPException(status_code=503, detail="Missed-lead service not configured")
    adapter = RetellWebhookAdapter(svc)
    result = await adapter.handle(payload)
    duplicate = getattr(result, "metadata", {}).get("duplicate", False) if hasattr(result, "metadata") else False
    return {
        "ok": bool(getattr(result, "success", False)),
        "duplicate": duplicate,
        "lead_id": str(getattr(getattr(result, "data", None), "id", "") or ""),
    }


@router.post("/{tenant_id}/webhooks/vapi/call")
async def vapi_missed_call_webhook(
    tenant_id: str = PathParam(..., description="Tenant identifier"),
    payload: dict[str, Any] = Body(...),
):
    """Vapi.ai missed-call webhook. Feeds shared.missed_lead recovery flow."""
    if not _HAS_MISSED_LEAD:
        raise HTTPException(status_code=503, detail="Missed-lead service not available")
    svc = _get_missed_lead_service(tenant_id)
    if svc is None:
        raise HTTPException(status_code=503, detail="Missed-lead service not configured")
    adapter = VapiWebhookAdapter(svc)
    result = await adapter.handle(payload)
    duplicate = getattr(result, "metadata", {}).get("duplicate", False) if hasattr(result, "metadata") else False
    return {
        "ok": bool(getattr(result, "success", False)),
        "duplicate": duplicate,
        "lead_id": str(getattr(getattr(result, "data", None), "id", "") or ""),
    }


@router.post("/{tenant_id}/webhooks/bland/call")
async def bland_missed_call_webhook(
    tenant_id: str = PathParam(..., description="Tenant identifier"),
    payload: dict[str, Any] = Body(...),
):
    """Bland.ai missed-call webhook. Feeds shared.missed_lead recovery flow."""
    if not _HAS_MISSED_LEAD:
        raise HTTPException(status_code=503, detail="Missed-lead service not available")
    svc = _get_missed_lead_service(tenant_id)
    if svc is None:
        raise HTTPException(status_code=503, detail="Missed-lead service not configured")
    adapter = BlandWebhookAdapter(svc)
    result = await adapter.handle(payload)
    duplicate = getattr(result, "metadata", {}).get("duplicate", False) if hasattr(result, "metadata") else False
    return {
        "ok": bool(getattr(result, "success", False)),
        "duplicate": duplicate,
        "lead_id": str(getattr(getattr(result, "data", None), "id", "") or ""),
    }


@router.post("/{tenant_id}/webhooks/whatsapp/message")
async def whatsapp_missed_lead_webhook(
    tenant_id: str = PathParam(..., description="Tenant identifier"),
    payload: dict[str, Any] = Body(...),
    request: Request = None,
):
    """Meta WhatsApp Cloud webhook for missed-lead reply handling.
    
    Feeds inbound WhatsApp replies into shared.missed_lead.handle_reply for
    qualification and booking. Verifies webhook signature via WhatsAppLeadResponder.
    """
    if not _HAS_MISSED_LEAD:
        raise HTTPException(status_code=503, detail="Missed-lead service not available")
    svc = _get_missed_lead_service(tenant_id)
    if svc is None:
        raise HTTPException(status_code=503, detail="Missed-lead service not configured")
    
    # Verify webhook signature if responder has WhatsApp channel
    if hasattr(svc, '_responder') and svc._responder is not None:
        responder = svc._responder
        if hasattr(responder, 'validate_webhook'):
            body = await request.body()
            headers = dict(request.headers)
            if not await responder.validate_webhook(body, headers):
                raise HTTPException(status_code=401, detail="Invalid WhatsApp webhook signature")
    
    # Parse inbound message using responder's parser
    if hasattr(svc._responder, 'parse_inbound'):
        try:
            message = await svc._responder.parse_inbound(payload, dict(request.headers))
            # Extract caller number and text from parsed message
            caller_number = getattr(message, 'customer_contact', '') or getattr(message, 'customer_id', '')
            text = getattr(message, 'content', '') or ''
            provider_msg_id = getattr(message, 'message_id', None)
            
            if caller_number and text:
                result = await svc.handle_reply(
                    caller_number=caller_number,
                    text=text,
                    provider_message_id=provider_msg_id,
                )
                return {
                    "ok": bool(getattr(result, "success", False)),
                    "lead_id": str(getattr(getattr(result, "data", None), "id", "") or ""),
                    "qualified": getattr(getattr(result, "data", None), "status", "") in ("qualified", "booked", "recovered"),
                }
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"WhatsApp message parse failed: {exc}") from exc
    
    # Fallback: try to extract from raw payload (WhatsApp Cloud format)
    try:
        entry = payload.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        if messages:
            msg = messages[0]
            caller_number = msg.get("from", "")
            text = msg.get("text", {}).get("body", "") if msg.get("type") == "text" else ""
            provider_msg_id = msg.get("id", "")
            if caller_number and text:
                result = await svc.handle_reply(
                    caller_number=caller_number,
                    text=text,
                    provider_message_id=provider_msg_id,
                )
                return {
                    "ok": bool(getattr(result, "success", False)),
                    "lead_id": str(getattr(getattr(result, "data", None), "id", "") or ""),
                    "qualified": getattr(getattr(result, "data", None), "status", "") in ("qualified", "booked", "recovered"),
                }
    except Exception:
        pass
    
    return {"ok": False, "error": "Could not parse WhatsApp message"}


# ── call list (dashboard) ──────────────────────────────────────────────

@router.get("/{tenant_id}/calls", response_model=CallListResponse)
async def list_calls_endpoint(
    tenant_id: str = PathParam(..., description="Tenant identifier"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _auth: dict = Depends(require_tenant_access),
):
    """List a tenant's voice calls for the CallLog dashboard."""
    calls = list_tenant_calls(tenant_id=tenant_id, limit=limit, offset=offset)
    return CallListResponse(
        tenant_id=tenant_id,
        calls=calls,
        limit=limit,
        offset=offset,
    )


@router.get("/{tenant_id}/calls/{call_sid}")
async def get_call(
    tenant_id: str = PathParam(..., description="Tenant identifier"),
    call_sid: str = PathParam(..., description="Twilio Call SID"),
    _auth: dict = Depends(require_tenant_access),
):
    """Get a single call record (includes recording URL + extracted fields)."""
    call = get_call_by_sid(call_sid)
    if not call or call["tenant_id"] != tenant_id:
        raise HTTPException(status_code=404, detail="Call not found")
    return call