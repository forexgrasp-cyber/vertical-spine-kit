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

SERVICE_NAME = "vertical-spine-kit"
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
from services.tenant_resolver import resolve_tenant
from shared.metrics.analytics_router import build_metrics_router
from shared.web.seo_surfaces import create_seo_router

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

SERVICE_NAME = "vertical-spine-kit"

app = FastAPI(
    title="Vertical Spine Kit API",
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
app.include_router(
    create_seo_router(project_root=Path(__file__).parent, vertical_id="vertical-spine-kit")
)
if i18n_router is not None:
    app.include_router(i18n_router)
if license_router is not None:
    app.include_router(license_router, prefix="/api/v1/licenses", tags=["licenses"])
if booking_router is not None:
    app.include_router(booking_router, prefix="/api/v1/bookings", tags=["bookings"])

# Tenant-scoped business metrics: users read THEIR OWN KPIs at
# /api/v1/metrics - the resolver maps the platform session to the caller's
# tenant (services/tenant_resolver.py; unauthenticated => 401).
app.include_router(build_metrics_router(project="vertical-spine-kit", tenant_resolver=resolve_tenant))

# Authentication: hub at snapford.com/auth is the CANONICAL identity
# provider (parent-domain SSO cookies on .snapford.com). The vertical's
# auth_routes are for DEV/TEST only (contract tests, local development).
# In production, users sign in at snapford.com and the session cookie
# flows to this subdomain automatically via AUTH_COOKIE_DOMAIN=.snapford.com.
from api.routes.auth_routes import router as auth_router
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication (dev)"])

# Production feature routers (conditional on availability)
if _HAS_SSO:
    app.include_router(sso_router, prefix="/api/auth/sso", tags=["Enterprise SSO"])
    app.include_router(saml_router, prefix="/api/auth/saml", tags=["SAML SSO"])

if _HAS_INTEGRATIONS:
    from shared.integrations.router import router as integrations_router
    app.include_router(integrations_router, prefix="/api/v1/integrations", tags=["Integrations"])

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
