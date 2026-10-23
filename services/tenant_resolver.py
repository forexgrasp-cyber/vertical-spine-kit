"""Tenant resolution for the tenant-scoped metrics API.

Default scope: the signed-in platform user IS the tenant (per-user
analytics). When this product gains org-level tenants (like janitorial
crews sharing an account), map the platform session to the caller's org id
from your users table here - and never return a tenant id the caller does
not belong to. No session / no hub configured => None => the metrics API
answers 401 (fail closed); hub unreachable => HubSessionError propagates
(500, also fail closed, and visible in logs instead of a fake 401).
"""

from __future__ import annotations

from fastapi import Request

from shared.auth.platform_sso import (
    SESSION_COOKIE,
    HubSessionClient,
    resolve_hub_session,
)

_client = HubSessionClient()  # hub URL from SNAPFORD_HUB_INTERNAL_URL


async def resolve_tenant(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    session = await resolve_hub_session(_client, token)
    return session.user_id if session else None
