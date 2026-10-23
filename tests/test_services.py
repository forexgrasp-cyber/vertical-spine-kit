# tests/test_services.py
# Service layer tests for vertical SaaS product.

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.tenant_resolver import resolve_tenant
from shared.auth.platform_sso import SESSION_COOKIE


@pytest.mark.asyncio
async def test_resolve_tenant_returns_none_when_no_cookie():
    """resolve_tenant should return None when no session cookie present."""
    from fastapi import Request

    request = MagicMock(spec=Request)
    request.cookies = {}

    tenant = await resolve_tenant(request)
    assert tenant is None


@pytest.mark.asyncio
async def test_resolve_tenant_returns_user_id_when_valid_session():
    """resolve_tenant should return user_id when valid session exists."""
    from fastapi import Request

    with patch("services.tenant_resolver._client") as mock_client:
        with patch("services.tenant_resolver.resolve_hub_session", new_callable=AsyncMock) as mock_resolve:
            mock_session = MagicMock()
            mock_session.user_id = "user-123"
            mock_resolve.return_value = mock_session

            request = MagicMock(spec=Request)
            request.cookies = {SESSION_COOKIE: "valid-token"}

            tenant = await resolve_tenant(request)
            assert tenant == "user-123"
            mock_resolve.assert_awaited_once_with(mock_client, "valid-token")


@pytest.mark.asyncio
async def test_resolve_tenant_returns_none_when_invalid_session():
    """resolve_tenant should return None when session is invalid."""
    from fastapi import Request

    with patch("services.tenant_resolver._client") as mock_client:
        with patch("services.tenant_resolver.resolve_hub_session", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = None

            request = MagicMock(spec=Request)
            request.cookies = {SESSION_COOKIE: "invalid-token"}

            tenant = await resolve_tenant(request)
            assert tenant is None
