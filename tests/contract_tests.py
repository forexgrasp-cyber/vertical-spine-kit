"""Contract tests for API compatibility across verticals.

Two tiers:
- VerticalContractTestBase: CORE contracts every vertical must pass
  (health, readiness, SEO surfaces, i18n, OpenAPI docs).
- AuthContractTestBase: AUTH contracts for verticals with auth routes
  (register/verify/login flow, token refresh, JWT-protected /me).

Existing scaffold-only verticals implement only core contracts.
Verticals with auth implement both.
"""

from __future__ import annotations

import time
import uuid

import pytest
from fastapi.testclient import TestClient


class VerticalContractTestBase:
    """Core contract tests that ALL verticals must pass."""

    @pytest.fixture
    def client(self):
        raise NotImplementedError("Subclasses must implement client fixture")

    def test_health_endpoint(self, client):
        """All verticals must have /api/health endpoint."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data

    def test_ready_endpoint(self, client):
        """All verticals must have /api/ready endpoint."""
        response = client.get("/api/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert "service" in data

    def test_info_endpoint(self, client):
        """All verticals must have /api/info endpoint (if present in scaffold)."""
        response = client.get("/api/info")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data

    def test_seo_surfaces(self, client):
        """All verticals must have canonical SEO surfaces."""
        # sitemap.xml
        resp = client.get("/sitemap.xml")
        assert resp.status_code == 200
        assert "xml" in resp.headers.get("content-type", "")
        assert "<urlset" in resp.text

        # robots.txt
        resp = client.get("/robots.txt")
        assert resp.status_code == 200
        assert "User-agent" in resp.text

        # SEO manifest
        resp = client.get("/api/seo/manifest")
        assert resp.status_code == 200

        # Design tokens
        resp = client.get("/api/seo/style/tokens.css")
        assert resp.status_code == 200
        assert "css" in resp.headers.get("content-type", "")

    def test_seo_surfaces_content(self, client):
        """SEO surfaces must have expected content."""
        # Sitemap should have at least one URL
        resp = client.get("/sitemap.xml")
        assert "<url>" in resp.text
        assert "<loc>" in resp.text

        # Robots.txt should have proper format
        resp = client.get("/robots.txt")
        assert "User-agent:" in resp.text

        # Design tokens should have CSS variables
        resp = client.get("/api/seo/style/tokens.css")
        assert ":root" in resp.text

    def test_i18n_endpoints(self, client):
        """All verticals must have i18n endpoints."""
        from shared.i18n import PLATFORM_LOCALES

        # Languages endpoint
        resp = client.get("/api/i18n/languages")
        assert resp.status_code == 200
        data = resp.json()
        assert set(data["languages"]) == set(PLATFORM_LOCALES)
        assert data["dirs"]["ar"] == "rtl"

        # Translations endpoint (spot-check 3 locales)
        for locale in PLATFORM_LOCALES[:3]:
            resp = client.get(f"/api/i18n/translations/{locale}")
            assert resp.status_code == 200

    def test_openapi_docs(self, client):
        """All verticals must have OpenAPI schema accessible."""
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "openapi" in data
        assert "paths" in data

    def test_swagger_ui(self, client):
        """Swagger UI must be accessible in non-production."""
        import os
        if os.getenv("APP_ENV") != "production":
            resp = client.get("/docs")
            assert resp.status_code == 200

    def test_redoc(self, client):
        """ReDoc must be accessible in non-production."""
        import os
        if os.getenv("APP_ENV") != "production":
            resp = client.get("/redoc")
            assert resp.status_code == 200

    def test_landing_page(self, client):
        """Landing page must render (SPA or static)."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "html" in resp.headers.get("content-type", "").lower()


class AuthContractTestBase(VerticalContractTestBase):
    """Auth contract tests for verticals with authentication routes.

    These run IN ADDITION to the core contracts. Only verticals
    with /api/auth/* routes should inherit from this class.
    """

    @staticmethod
    def _unique_email(prefix: str) -> str:
        """Collision-resistant unique email (auth is now persistent)."""
        return f"{prefix}_{int(time.time())}_{uuid.uuid4().hex[:8]}@example.com"

    @staticmethod
    def _auth_headers(client: TestClient) -> dict:
        """Dev-login and return Bearer headers (for protected endpoints)."""
        resp = client.post("/api/auth/dev-login")
        assert resp.status_code == 200, resp.text
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_dev_login(self, client):
        """Development login must work."""
        resp = client.post("/api/auth/dev-login")
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_register_verify_login_flow(self, client):
        """Register -> verify -> login flow must work with JSON bodies."""
        email = self._unique_email("contract")

        # Register (JSON body; response includes verification_token + user_id)
        resp = client.post("/api/auth/register", json={
            "email": email,
            "password": "TestPass123!",
            "name": "Contract Test",
        })
        assert resp.status_code == 201, resp.text
        reg_data = resp.json()
        assert "verification_token" in reg_data
        assert "user_id" in reg_data

        # Verify email (JSON body)
        resp = client.post("/api/auth/verify-email", json={
            "token": reg_data["verification_token"],
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "verified"

        # Login (JSON body)
        resp = client.post("/api/auth/login", json={
            "email": email,
            "password": "TestPass123!",
        })
        assert resp.status_code == 200, resp.text
        tokens = resp.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens

    def test_token_refresh(self, client):
        """Token refresh must work with JSON body."""
        email = self._unique_email("refresh")

        # Register + verify
        reg = client.post("/api/auth/register", json={
            "email": email,
            "password": "TestPass123!",
            "name": "Refresh Test",
        })
        reg_data = reg.json()
        client.post("/api/auth/verify-email", json={
            "token": reg_data["verification_token"],
        })

        # Login to get refresh token
        login = client.post("/api/auth/login", json={
            "email": email,
            "password": "TestPass123!",
        })
        refresh_token = login.json()["refresh_token"]

        # Refresh
        resp = client.post("/api/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "access_token" in data

        # Old refresh token must be revoked after rotation
        resp2 = client.post("/api/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert resp2.status_code == 401, "refresh token must be single-use"

    def test_logout(self, client):
        """Logout must be callable WITH a valid token."""
        headers = self._auth_headers(client)
        resp = client.post("/api/auth/logout", headers=headers)
        assert resp.status_code == 200

    def test_me_endpoint(self, client):
        """GET /api/auth/me must return user info WITH a valid token."""
        headers = self._auth_headers(client)
        resp = client.get("/api/auth/me", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" in data or "email" in data

    # --- Negative auth tests (real JWT validation) ---

    def test_me_without_token_401(self, client):
        """GET /api/auth/me without a token must be 401."""
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_with_garbage_token_401(self, client):
        """GET /api/auth/me with an invalid token must be 401."""
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer not-a-real-jwt-token"},
        )
        assert resp.status_code == 401

    def test_login_wrong_password_401(self, client):
        """Login with a wrong password must be 401 (not 500)."""
        email = self._unique_email("wrongpw")
        client.post("/api/auth/register", json={
            "email": email,
            "password": "CorrectPass123!",
            "name": "Wrong PW Test",
        })
        resp = client.post("/api/auth/login", json={
            "email": email,
            "password": "WrongPass123!",
        })
        assert resp.status_code == 401

    def test_duplicate_register_400(self, client):
        """Registering the same email twice must be 400 (not 500)."""
        email = self._unique_email("dupe")
        payload = {
            "email": email,
            "password": "TestPass123!",
            "name": "Dupe Test",
        }
        first = client.post("/api/auth/register", json=payload)
        assert first.status_code == 201
        second = client.post("/api/auth/register", json=payload)
        assert second.status_code == 400


class DomainCRUDContractMixin:
    """Entity CRUD contract tests. The concrete test class must set:

    - crud_endpoint: URL segment, e.g. "boats" (mounted at /api/v1/<endpoint>)
    - crud_payload: base create payload (unique fields auto-suffixed)
    - crud_unique_fields: fields that must be unique per run (default: ["name"])
    - crud_update_payload: fields to patch in the update step
    """

    crud_endpoint: str = ""
    crud_payload: dict = {}
    crud_unique_fields: list = ["name"]
    crud_update_payload: dict = {}

    @staticmethod
    def _crud_suffix() -> str:
        return uuid.uuid4().hex[:10]

    def _crud_auth_headers(self, client):
        resp = client.post("/api/auth/dev-login")
        assert resp.status_code == 200, resp.text
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    def _crud_create_payload(self) -> dict:
        payload = dict(self.crud_payload)
        suffix = self._crud_suffix()
        for field in self.crud_unique_fields:
            if field in payload and isinstance(payload[field], str):
                value = payload[field]
                if "@" in value:
                    local, _, domain = value.partition("@")
                    payload[field] = f"{local}-{suffix}@{domain}"
                else:
                    payload[field] = f"{value}-{suffix}"
        return payload

    def test_domain_crud_flow(self, client):
        """Create -> read -> list -> update -> delete -> verify soft state."""
        if not self.crud_endpoint:
            pytest.skip("no crud endpoint configured")
        headers = self._crud_auth_headers(client)
        base = f"/api/v1/{self.crud_endpoint}"
        payload = self._crud_create_payload()

        # Create
        resp = client.post(base, json=payload, headers=headers)
        assert resp.status_code == 201, resp.text
        created = resp.json()
        assert created.get("id")
        assert created["status"] in ("active", "pending")
        for field in self.crud_unique_fields:
            assert created[field] == payload[field]

        # Read by id
        resp = client.get(f"{base}/{created['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

        # List contains it
        resp = client.get(base, headers=headers)
        assert resp.status_code == 200
        ids = [i["id"] for i in resp.json()["items"]]
        assert created["id"] in ids

        # Update
        if self.crud_update_payload:
            resp = client.patch(
                f"{base}/{created['id']}", json=self.crud_update_payload, headers=headers
            )
            assert resp.status_code == 200, resp.text
            for field, value in self.crud_update_payload.items():
                assert resp.json()[field] == value

        # Delete (soft)
        resp = client.delete(f"{base}/{created['id']}", headers=headers)
        assert resp.status_code == 204

        # Verify soft-deleted state via direct read
        resp = client.get(f"{base}/{created['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] in ("archived", "terminated")

        # Verify excluded from default listing
        resp = client.get(base, headers=headers)
        ids = [i["id"] for i in resp.json()["items"]]
        assert created["id"] not in ids, "archived item must be hidden from default list"

    def test_domain_crud_requires_auth(self, client):
        """Entity API must reject unauthenticated create with 401."""
        if not self.crud_endpoint:
            pytest.skip("no crud endpoint configured")
        resp = client.post(
            f"/api/v1/{self.crud_endpoint}", json=self._crud_create_payload()
        )
        assert resp.status_code == 401

    def test_domain_crud_missing_404(self, client):
        """Reading a nonexistent entity must be 404 (not 500)."""
        if not self.crud_endpoint:
            pytest.skip("no crud endpoint configured")
        headers = self._crud_auth_headers(client)
        resp = client.get(
            f"/api/v1/{self.crud_endpoint}/00000000-0000-0000-0000-000000000000",
            headers=headers,
        )
        assert resp.status_code == 404