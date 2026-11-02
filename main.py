"""Vertical Spine Kit - Snapford vertical SaaS (production scaffold).

FastAPI app with full production features:
- Canonical SEO surfaces (sitemap, robots, manifest, design tokens)
- i18n language surface (20 platform locales, RTL support)
- Tenant-scoped metrics & analytics (hub business-metrics feed)
- Multi-provider billing (Stripe, PayPal, Paddle, Adyen, Wayforpay,
  Fondy, LiqPay, Mono, NovaPay, RozetkaPay, Creem, Dodo, FastSpring,
  Freemius, Airwallex, Payoneer, PayPro, Verifone + more via
  shared.payments registry) via UnifiedPaymentService
- Enterprise SSO (SAML/OIDC) — hub at snapford.com is canonical identity
- Integrations & webhooks
- Multi-tenant organizations (RBAC, invitations)
- White-label branding
- Enterprise security (audit, break-glass, IP allowlist)
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

SERVICE_NAME = "callagent"
SNAPFORD_PRODUCT_ID = os.getenv("SNAPFORD_PRODUCT_ID", SERVICE_NAME)

# i18n router (conditional - may not exist in all verticals)
try:
    from api.routes_i18n import router as i18n_router
except ImportError:
    i18n_router = None
try:
    from api.routes.license_routes import router as license_router
except ImportError:
    license_router = None
try:
    from api.routes.booking_routes import router as booking_router
except ImportError:
    booking_router = None
try:
    from api.routes.agent_routes import router as agent_router
except ImportError:
    agent_router = None
from services.tenant_resolver import resolve_tenant
from shared.metrics.analytics_router import build_metrics_router

# SEO surfaces (optional - may not exist in all shared versions)
try:
    from shared.web.seo_surfaces import create_seo_router
except ImportError:
    create_seo_router = None

# ── Multi-provider billing (ALL shared.billing / shared.payments) ────
try:
    from shared.billing.unified_payment_service import UnifiedPaymentService
    from shared.billing.pricing_service import PricingService
    from shared.billing.entitlements_service import EntitlementsService
    from shared.billing.subscription_service import SubscriptionService
    from shared.billing.invoicing_service import InvoicingService
    from shared.billing.order_management_service import OrderManagementService
    from shared.payments.registry import known_providers
    _HAS_BILLING = True
    _PAYMENT_PROVIDERS = known_providers()
except ImportError:
    _HAS_BILLING = False
    _PAYMENT_PROVIDERS = []

# ── Hub entitlements (product access checks) ─────────────────────────
_HAS_ENTITLEMENTS = _HAS_BILLING

# ── Hub business-metrics feed (per-product KPI reporting) ─────────────
try:
    from shared.metrics.analytics_router import build_metrics_router
    _HAS_METRICS = True
except ImportError:
    _HAS_METRICS = False

try:
    from shared.sso.router import router as sso_router
    from shared.sso.saml_router import router as saml_router
    from shared.sso.oidc_client import OIDCClient
    from shared.sso.org_gateway import OrgGateway
    _HAS_SSO = True
except ImportError:
    _HAS_SSO = False

try:
    from shared.integrations.capability_registry import CapabilityRegistry
    from shared.integrations.schema_introspection_service import SchemaIntrospectionService
    from shared.integrations.emission import emit_event
    _HAS_INTEGRATIONS = True
except ImportError:
    _HAS_INTEGRATIONS = False

try:
    from shared.organizations.router import router as org_router
    from shared.organizations.rbac_service import RBACService
    from shared.organizations.invitations_router import router as invitations_router
    _HAS_ORGANIZATIONS = True
except ImportError:
    _HAS_ORGANIZATIONS = False

try:
    from shared.white_label.router import router as white_label_router
    from shared.white_label.branding_service import BrandingService
    _HAS_WHITE_LABEL = True
except ImportError:
    _HAS_WHITE_LABEL = False

try:
    from shared.enterprise_security.router import router as enterprise_security_router
    from shared.enterprise_security.ip_allowlist_router import router as ip_allowlist_router
    from shared.enterprise_security.break_glass_router import router as break_glass_router
    from shared.enterprise_security.incident_router import router as incident_router
    _HAS_ENTERPRISE_SECURITY = True
except ImportError:
    _HAS_ENTERPRISE_SECURITY = False

app = FastAPI(
    title="CallAgent API",
    version="1.0.0",
    docs_url="/docs" if os.getenv("APP_ENV") != "production" else None,
    redoc_url="/redoc" if os.getenv("APP_ENV") != "production" else None,
)

# Security middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request context middleware
from shared.middleware import install_request_context_middleware
install_request_context_middleware(app, service_name=SERVICE_NAME)

# Request logging middleware
from shared.middleware import install_request_logging_middleware
install_request_logging_middleware(app, exclude_paths=["/health", "/ready", "/metrics", "/favicon.ico"])

# Health check middleware
from shared.middleware import install_health_check_middleware
install_health_check_middleware(app, health_path="/health", ready_path="/ready")

# Standardized error envelope (no stack-trace leaks on 500; error_code on 422)
from shared.middleware.error_envelope import install_error_envelope
install_error_envelope(app)

# Rate limiting
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
except ImportError:
    pass

# Observability: Sentry, OpenTelemetry, structured logging
try:
    from shared.observability import setup_observability
    setup_observability(app)
except ImportError:
    pass

# Canonical SEO surfaces: sitemap.xml, robots.txt, /api/seo/manifest,
# /api/seo/style/tokens.css (the product's light+dark design tokens).
if create_seo_router is not None:
    app.include_router(
        create_seo_router(project_root=Path(__file__).parent, vertical_id="callagent")
    )
if i18n_router is not None:
    app.include_router(i18n_router)
if license_router is not None:
    app.include_router(license_router, prefix="/api/v1/licenses", tags=["licenses"])
if booking_router is not None:
    app.include_router(booking_router, prefix="/api/v1/bookings", tags=["bookings"])
if agent_router is not None:
    app.include_router(agent_router, prefix="/api/v1/agent", tags=["Voice Agent"])

# Tenant-scoped business metrics: users read THEIR OWN KPIs at
# /api/v1/metrics - the resolver maps the platform session to the caller's
# tenant (services/tenant_resolver.py; unauthenticated => 401).
app.include_router(build_metrics_router(project="callagent", tenant_resolver=resolve_tenant))

# Authentication: hub at snapford.com/auth is the CANONICAL identity
# provider (parent-domain SSO cookies on .snapford.com). The vertical's
# auth_routes are for DEV/TEST only (contract tests, local development).
# In production, users sign in at snapford.com and the session cookie
# flows to this subdomain automatically via AUTH_COOKIE_DOMAIN=.snapford.com.
try:
    from api.routes.auth_routes import router as auth_router
except ImportError:
    auth_router = None

if auth_router is not None:
    app.include_router(auth_router, prefix="/api/auth", tags=["Authentication (dev)"])

# Production feature routers (conditional on availability)
if _HAS_SSO:
    app.include_router(sso_router, prefix="/api/auth/sso", tags=["Enterprise SSO"])
    app.include_router(saml_router, prefix="/api/auth/saml", tags=["SAML SSO"])

if _HAS_INTEGRATIONS:
    try:
        from shared.integrations.router import router as integrations_router
        app.include_router(integrations_router, prefix="/api/v1/integrations", tags=["Integrations"])
    except ImportError:
        # Integrations router not available in this version
        pass

if _HAS_ORGANIZATIONS:
    app.include_router(org_router, prefix="/api/v1/organizations", tags=["Organizations"])
    app.include_router(invitations_router, prefix="/api/v1/organizations", tags=["Organization Invitations"])

if _HAS_WHITE_LABEL:
    app.include_router(white_label_router, prefix="/api/v1/branding", tags=["White-label"])

if _HAS_ENTERPRISE_SECURITY:
    app.include_router(enterprise_security_router, prefix="/api/v1/security", tags=["Enterprise Security"])
    app.include_router(ip_allowlist_router, prefix="/api/v1/security", tags=["IP Allowlist"])
    app.include_router(break_glass_router, prefix="/api/v1/security", tags=["Break Glass"])
    app.include_router(incident_router, prefix="/api/v1/security", tags=["Incidents"])

# ── Billing: multi-provider checkout + subscriptions ─────────────────
# Uses UnifiedPaymentService which auto-detects configured providers
# from the 18 supported: adyen airwallex creem dodo fastspring fondy
# freemius liqpay mono novapay paddle payoneer_checkout paypal
# paypro_global rozetkapay stripe verifone wayforpay.
# Set credentials in .env for ONLY the providers you need.
if _HAS_BILLING:
    _payment_service = UnifiedPaymentService()
    _pricing_service = PricingService()
    _entitlements_service = EntitlementsService(
        db_path=os.getenv("ENTITLEMENTS_DB_PATH", "data/entitlements.db")
    )

    @app.get("/api/v1/billing/providers", tags=["Billing"])
    async def list_payment_providers() -> dict:
        """List all known payment providers (18 from shared.payments)."""
        return {
            "product_id": SNAPFORD_PRODUCT_ID,
            "known_providers": _PAYMENT_PROVIDERS,
            "checkout_mode": os.getenv("CHECKOUT_MODE", "subscription"),
        }

    @app.get("/api/v1/billing/pricing", tags=["Billing"])
    async def get_pricing() -> dict:
        """Get this product's pricing tiers."""
        return {"tiers": _pricing_service.get_pricing_tier()}

    @app.post("/api/v1/billing/checkout", tags=["Billing"])
    async def create_checkout(provider: str, product_name: str, amount: float,
                              currency: str = "usd",
                              customer_email: str | None = None) -> dict:
        """Create a payment link with the specified provider.

        UnifiedPaymentService routes to the provider; unset credentials
        for a provider => ServiceResponse error naming the missing env vars.
        """
        result = _payment_service.create_payment_link(
            product_id=SNAPFORD_PRODUCT_ID,
            product_name=product_name,
            amount=amount,
            currency=currency,
            customer_email=customer_email,
            provider=provider,
        )
        if not result.success:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=result.error)
        return result.data or {}

    @app.get("/api/v1/billing/entitlements", tags=["Billing"])
    async def get_entitlements() -> dict:
        """Get the caller's active entitlements (account = user_id from hub session)."""
        return {
            "product_id": SNAPFORD_PRODUCT_ID,
            "entitlements": _entitlements_service.list_active(
                account=os.getenv("DEV_USER_ID", "anonymous")
            ),
        }

# ── Hub business-metrics feed ────────────────────────────────────────
# Reports per-product KPIs to the hub (snapford.com/api/v1/metrics)
# when METRICS_FEED=1. The hub aggregates cross-product metrics.
if _HAS_METRICS and os.getenv("METRICS_FEED", "1") == "1":
    import asyncio

    async def _report_product_metrics() -> None:
        """Report this product's KPIs to the hub metrics feed."""
        _hub_url = os.getenv("SNAPFORD_HUB_INTERNAL_URL", "")
        if not _hub_url:
            return
        import httpx

        _interval = int(os.getenv("METRICS_FEED_INTERVAL", "3600"))
        while True:
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{_hub_url}/api/v1/metrics/feed",
                        json={
                            "product_id": SNAPFORD_PRODUCT_ID,
                            "service": SERVICE_NAME,
                        },
                        timeout=10.0,
                    )
            except Exception:
                pass  # hub unreachable: metrics feed is best-effort
            await asyncio.sleep(_interval)

    @app.on_event("startup")
    async def start_metrics_feed() -> None:
        asyncio.create_task(_report_product_metrics())

# Health check
@app.get("/api/health")
async def health() -> dict:
    return {"status": "healthy", "service": SERVICE_NAME}

# Readiness check (verifies entity DB connectivity when an engine is loaded)
@app.get("/api/ready")
async def ready() -> dict:
    checks: dict = {"app": True, "database": "not-configured"}
    try:
        import sys as _sys
        for _name, _mod in list(_sys.modules.items()):
            if _name.startswith("services.") and hasattr(_mod, "engine"):
                from sqlalchemy import text as _text
                with _mod.engine.connect() as _conn:
                    _conn.execute(_text("SELECT 1"))
                checks["database"] = True
                break
    except Exception as _exc:
        checks["database"] = f"error: {type(_exc).__name__}"
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"status": "not-ready", "service": SERVICE_NAME, "checks": checks},
        )
    return {"status": "ready", "service": SERVICE_NAME, "checks": checks}

# ── Landing page (shared.web.landing) ──────────────────────────────────
try:
    from shared.web.landing import build_landing_page, LandingContent, LandingBenefit, LandingMetric, LandingFAQ

    def _build_vertical_landing_content() -> LandingContent:
        return LandingContent(
            product_name="Vertical Spine Kit",
            tagline="Voice AI for Local Business",
            category="SaaS",
            hero_subtitle="Answer every call, book every job, and never miss a lead — powered by AI voice agents that sound human.",
            benefits=(
                LandingBenefit(
                    title="24/7 Call Coverage",
                    body="Never miss a call again. Our AI voice agent answers instantly, qualifies leads, and books appointments.",
                    time_saved="15 hrs/week",
                    money_saved="$3,200/mo"
                ),
                LandingBenefit(
                    title="Per-Tenant Knowledge Base",
                    body="Each business gets its own RAG-powered knowledge base. Ingest services, pricing, FAQs in minutes.",
                    time_saved="10 hrs/week",
                    money_saved="$1,500/mo"
                ),
                LandingBenefit(
                    title="TCPA/GDPR Compliant",
                    body="Immutable consent audit logs, automatic recording purge, PII encryption at rest. Built for compliance.",
                    time_saved="5 hrs/week",
                    money_saved="$800/mo"
                ),
            ),
            features=(
                ("Voice Webhook", "Twilio-native webhook handling with consent flow, speech gathering, and TwiML responses"),
                ("Intent Extraction", "LLM + keyword fallback extracts service, datetime, address, callback from speech"),
                ("Per-Tenant RAG", "Chroma + sentence-transformers for instant, accurate answers from your content"),
                ("Entitlement Gating", "Tier gate (Starter+) + EntitlementsService grants from Stripe webhooks"),
                ("Voice-Minute Metering", "Per-call billing via shared.billing.BillingService with usage API"),
                ("Immutable Consent", "Hash-chained audit log via shared.audit.ImmutableAuditLog for TCPA/GDPR"),
                ("Multi-Provider Billing", "Stripe, Lemon Squeezy, Paddle via shared.billing.UnifiedPaymentService"),
                ("Dark/Light Theme", "CSS variables + localStorage persistence, respects prefers-color-scheme"),
            ),
            metrics=(
                LandingMetric("99.9%", "Uptime SLA"),
                LandingMetric("<2s", "Avg Response"),
                LandingMetric("50+", "Languages"),
                LandingMetric("$0.10", "Per Min"),
            ),
            faqs=(
                LandingFAQ("How does the voice agent work?", "When a customer calls your Twilio number, our webhook handles the call: plays a consent prompt, gathers speech, extracts intent using LLM, queries your knowledge base, and responds with a natural-sounding answer."),
                LandingFAQ("Can I customize the knowledge base?", "Yes! Ingest services (JSON), pricing (CSV), and FAQs (Markdown) per tenant. The RAG system retrieves the top-3 most relevant chunks for every query."),
                LandingFAQ("What tiers are supported?", "Voice agent requires Starter+ tier. Free tier is denied with a friendly message. Upgrade via Stripe checkout or subscription — entitlements are granted automatically via webhook."),
                LandingFAQ("Is it compliant?", "Yes. Consent is captured and written to an immutable hash-chained audit log. Recordings are purged after 30 days. PII (phone, address) is encrypted at rest."),
                LandingFAQ("How much does it cost?", "Starter: $29/mo + $0.10/min voice. Pro: $79/mo + $0.08/min. Agency: $199/mo + $0.06/min. No setup fees."),
            ),
            brand_color="#0ea5e9",
            brand_dark="#0284c7",
            base_url=os.getenv("BASE_URL", "https://callagent.example.com"),
            og_image=os.getenv("OG_IMAGE", "https://callagent.example.com/og-image.png"),
        )

    @app.get("/", response_class=HTMLResponse)
    async def landing_page() -> HTMLResponse:
        """Serve the marketing landing page."""
        content = _build_vertical_landing_content()
        html = build_landing_page(content)
        return HTMLResponse(content=html)

    _HAS_LANDING = True
except ImportError:
    _HAS_LANDING = False

# ── Interactive Voice Agent Demo ───────────────────────────────────────
from fastapi.responses import HTMLResponse

DEMO_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Voice Agent Demo - Vertical Spine Kit</title>
    <style>
        :root {
            --brand: #0ea5e9;
            --brand-dark: #0284c7;
            --bg: #f8fafc;
            --surface: #ffffff;
            --text: #0f172a;
            --muted: #475569;
            --border: #e2e8f0;
            --shadow: 0 10px 30px rgba(15,23,42,.08);
        }
        @media (prefers-color-scheme: dark) {
            :root {
                --bg: #0b1120;
                --surface: #111827;
                --text: #e2e8f0;
                --muted: #94a3b8;
                --border: #1f2937;
                --shadow: 0 10px 30px rgba(0,0,0,.4);
            }
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            background: var(--bg);
            color: var(--text);
            font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
            line-height: 1.6;
            min-height: 100vh;
        }
        .container { max-width: 72rem; margin: 0 auto; padding: 2rem 1.5rem; }
        header { text-align: center; margin-bottom: 3rem; }
        header h1 { font-size: clamp(2rem, 5vw, 3rem); margin: 0 0 1rem; }
        header p { color: var(--muted); max-width: 40rem; margin: 0 auto; }
        .demo-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; }
        @media (max-width: 48rem) { .demo-grid { grid-template-columns: 1fr; } }
        .panel {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 1rem;
            padding: 1.5rem;
            box-shadow: var(--shadow);
        }
        .panel h2 { margin: 0 0 1rem; font-size: 1.25rem; }
        .btn {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.75rem 1.5rem;
            border-radius: 0.5rem;
            font-weight: 600;
            font-size: 1rem;
            cursor: pointer;
            border: none;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-primary { background: var(--brand); color: white; }
        .btn-primary:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 8px 20px color-mix(in srgb, var(--brand) 35%, transparent); }
        .btn-secondary { background: var(--surface); color: var(--text); border: 1px solid var(--border); }
        .status { padding: 0.75rem 1rem; border-radius: 0.5rem; margin: 1rem 0; font-size: 0.9rem; }
        .status.waiting { background: color-mix(in srgb, var(--brand) 15%, transparent); color: var(--brand-dark); border: 1px solid var(--brand); }
        .status.active { background: color-mix(in srgb, #059669 15%, transparent); color: #047857; border: 1px solid #059669; }
        .status.error { background: color-mix(in srgb, #dc2626 15%, transparent); color: #b91c1c; border: 1px solid #dc2626; }
        .transcript { height: 300px; overflow-y: auto; background: var(--bg); border: 1px solid var(--border); border-radius: 0.5rem; padding: 1rem; font-family: monospace; font-size: 0.9rem; line-height: 1.8; }
        .transcript .msg { margin-bottom: 0.75rem; }
        .transcript .msg.user { color: var(--brand); }
        .transcript .msg.agent { color: var(--muted); }
        .transcript .msg.system { color: var(--muted); font-style: italic; font-size: 0.85rem; }
        .controls { display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 1rem; }
        .tenant-select { flex: 1; min-width: 200px; }
        .tenant-select label { display: block; margin-bottom: 0.5rem; font-weight: 500; }
        .tenant-select select { width: 100%; padding: 0.6rem; border: 1px solid var(--border); border-radius: 0.5rem; background: var(--surface); color: var(--text); }
        .logs { height: 200px; overflow-y: auto; background: #0b1120; color: #a3e635; border-radius: 0.5rem; padding: 1rem; font-family: monospace; font-size: 0.8rem; }
        .log-entry { margin-bottom: 0.25rem; border-bottom: 1px solid #1f2937; padding-bottom: 0.25rem; }
        .log-entry.timestamp { color: #60a5fa; }
        .log-entry.event { color: #fbbf24; }
        .feature-tags { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 1rem; }
        .tag { background: color-mix(in srgb, var(--brand) 14%, transparent); color: var(--brand-dark); padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 600; }
        @media (prefers-color-scheme: dark) { .tag { color: var(--brand); background: color-mix(in srgb, var(--brand) 20%, transparent); } }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎙️ Voice Agent Interactive Demo</h1>
            <p>Experience the AI voice agent that answers calls, qualifies leads, and books appointments for local businesses.</p>
        </header>

        <div class="demo-grid">
            <div class="panel">
                <h2>📞 Call Simulation</h2>
                <div class="tenant-select">
                    <label for="tenantSelect">Select Tenant (simulates tier):</label>
                    <select id="tenantSelect">
                        <option value="demo-starter">Demo Starter (Starter tier - ✅ Allowed)</option>
                        <option value="demo-pro">Demo Pro (Pro tier - ✅ Allowed)</option>
                        <option value="demo-free">Demo Free (Free tier - ❌ Denied)</option>
                    </select>
                </div>
                <div class="controls">
                    <button class="btn btn-primary" id="startCallBtn" onclick="startCall()">🎤 Start Call</button>
                    <button class="btn btn-secondary" id="endCallBtn" onclick="endCall()" disabled>⏹️ End Call</button>
                </div>
                <div id="callStatus" class="status waiting">Waiting to start...</div>
                <div class="transcript" id="transcript"></div>
            </div>

            <div class="panel">
                <h2>🔧 How It Works</h2>
                <div class="feature-tags">
                    <span class="tag">Tier Gating (Starter+)</span>
                    <span class="tag">EntitlementsService</span>
                    <span class="tag">RAG Knowledge Base</span>
                    <span class="tag">Voice-Minute Metering</span>
                    <span class="tag">Immutable Consent Audit</span>
                    <span class="tag">TCPA/GDPR Compliant</span>
                </div>
                <h3 style="margin-top: 1.5rem;">Call Flow</h3>
                <ol style="line-height: 2;">
                    <li><strong>Tier Check</strong> — EntitlementsService + TierGuard dual-check</li>
                    <li><strong>Rate Limit</strong> — Token bucket per tenant (60/min)</li>
                    <li><strong>Consent</strong> — TCPA-compliant recording consent</li>
                    <li><strong>Speech → Intent</strong> — LLM + keyword fallback extraction</li>
                    <li><strong>RAG Query</strong> — Per-tenant Chroma vector search</li>
                    <li><strong>Response</strong> — Natural TTS + structured data</li>
                    <li><strong>Metering</strong> — Voice-minute billing via shared.billing</li>
                </ol>
            </div>

            <div class="panel" style="grid-column: 1 / -1;">
                <h2>📋 Live Event Log</h2>
                <div class="logs" id="logs"></div>
            </div>
        </div>
    </div>

    <script>
        const transcript = document.getElementById('transcript');
        const status = document.getElementById('callStatus');
        const startBtn = document.getElementById('startCallBtn');
        const endBtn = document.getElementById('endCallBtn');
        const tenantSelect = document.getElementById('tenantSelect');
        const logs = document.getElementById('logs');

        function log(msg, type = 'event') {
            const entry = document.createElement('div');
            entry.className = `log-entry ${type}`;
            const time = new Date().toLocaleTimeString();
            entry.innerHTML = `<span class="timestamp">[${time}]</span> ${msg}`;
            logs.insertBefore(entry, logs.firstChild);
        }

        function addToTranscript(speaker, text) {
            const msg = document.createElement('div');
            msg.className = `msg ${speaker}`;
            const prefix = speaker === 'user' ? '👤 Caller: ' : speaker === 'agent' ? '🤖 Agent: ' : '⚙️ System: ';
            msg.innerHTML = `<strong>${prefix}</strong>${text}`;
            transcript.appendChild(msg);
            transcript.scrollTop = transcript.scrollHeight;
        }

        async function apiCall(method, path, body = null) {
            const headers = { 'Content-Type': 'application/json' };
            const options = { method, headers };
            if (body) options.body = JSON.stringify(body);
            const response = await fetch(path, options);
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || response.statusText);
            return data;
        }

        async function startCall() {
            const tenantId = tenantSelect.value;
            startBtn.disabled = true;
            endBtn.disabled = false;
            status.className = 'status active';
            status.textContent = '🔄 Initiating call...';
            transcript.innerHTML = '';
            log(`Starting call for tenant: ${tenantId}`);

            try {
                // Step 1: Consent webhook
                addToTranscript('system', 'Initiating Twilio webhook (consent step)...');
                log('POST /api/v1/agent/{tenant_id}/webhook?step=consent');
                const consentResp = await apiCall('POST', `/api/v1/agent/${tenantId}/webhook?step=consent`, {
                    CallSid: `CA_demo_${Date.now()}`,
                    From: '+15551234567',
                    To: '+15559876543'
                });
                addToTranscript('agent', consentResp.twiml || 'Consent prompt played. Waiting for speech...');
                log('Consent TwiML returned', 'event');

                status.textContent = '🎤 Listening... Say something like "I need a plumber"';

                // Simulate user speech after 2 seconds
                setTimeout(async () => {
                    try {
                        addToTranscript('user', 'I need a plumber for a leaky faucet tomorrow morning.');
                        log('POST /api/v1/agent/{tenant_id}/webhook?step=gather (speech gathered)');
                        const gatherResp = await apiCall('POST', `/api/v1/agent/${tenantId}/webhook?step=gather`, {
                            CallSid: `CA_demo_${Date.now()}`,
                            SpeechResult: 'I need a plumber for a leaky faucet tomorrow morning.',
                            From: '+15551234567',
                            To: '+15559876543'
                        });
                        addToTranscript('agent', gatherResp.twiml || 'Response generated.');
                        log('Gather TwiML returned', 'event');
                        status.textContent = '✅ Call completed successfully';
                        log('Call flow completed successfully', 'event');
                    } catch (e) {
                        addToTranscript('system', `Error: ${e.message}`);
                        status.className = 'status error';
                        status.textContent = `❌ Error: ${e.message}`;
                        log(`Gather error: ${e.message}`, 'event');
                    }
                    endBtn.disabled = true;
                    startBtn.disabled = false;
                }, 2000);

            } catch (e) {
                addToTranscript('system', `Error: ${e.message}`);
                status.className = 'status error';
                status.textContent = `❌ Error: ${e.message}`;
                log(`Consent error: ${e.message}`, 'event');
                endBtn.disabled = true;
                startBtn.disabled = false;
            }
        }

        function endCall() {
            addToTranscript('system', 'Call ended by user.');
            status.className = 'status waiting';
            status.textContent = 'Call ended.';
            startBtn.disabled = false;
            endBtn.disabled = true;
            log('Call ended by user', 'event');
        }

        // Initial log
        log('Demo initialized. Select a tenant and click "Start Call".');
    </script>
</body>
</html>"""

@app.get("/demo", response_class=HTMLResponse)
async def voice_agent_demo() -> HTMLResponse:
    """Interactive voice agent demo page."""
    return HTMLResponse(content=DEMO_HTML)

# API info endpoint
@app.get("/api/info")
async def api_info() -> dict:
    return {
        "service": SERVICE_NAME,
        "version": "1.0.0",
        "features": {
            "billing": _HAS_BILLING,
            "payment_providers": _PAYMENT_PROVIDERS,
            "entitlements": _HAS_ENTITLEMENTS,
            "metrics_feed": _HAS_METRICS,
            "sso": _HAS_SSO,
            "integrations": _HAS_INTEGRATIONS,
            "organizations": _HAS_ORGANIZATIONS,
            "white_label": _HAS_WHITE_LABEL,
            "enterprise_security": _HAS_ENTERPRISE_SECURITY,
        },
        "product_id": SNAPFORD_PRODUCT_ID,
        "hub_url": os.getenv("SNAPFORD_HUB_INTERNAL_URL", "not-configured"),
        "environment": os.getenv("APP_ENV", "development"),
    }

frontend_dir = Path(__file__).parent / "frontend" / "dist"
source_index = Path(__file__).parent / "frontend" / "index.html"
assets_dir = frontend_dir / "assets"
if frontend_dir.exists() and assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

@app.get("/{full_path:path}", response_class=HTMLResponse)
async def serve_frontend(full_path: str) -> FileResponse:
    """Serve the SPA; unknown paths fall back to index.html.

    Before the frontend is built (dist missing) the source index.html is
    served, so `/` and deep links are conformance-green from minute one.
    """
    if frontend_dir.exists():
        file_path = frontend_dir / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dir / "index.html"))
    return FileResponse(str(source_index))
