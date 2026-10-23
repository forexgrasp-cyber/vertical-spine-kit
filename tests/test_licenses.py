"""Tests for vertical-spine-kit license keys (#5)."""

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def license_store(tmp_path):
    """Isolated JSON store per test."""
    path = tmp_path / "license_keys.json"
    path.write_text("[]", encoding="utf-8")
    old = os.environ.get("LICENSE_STORE_PATH")
    os.environ["LICENSE_STORE_PATH"] = str(path)
    yield path
    if old is None:
        os.environ.pop("LICENSE_STORE_PATH", None)
    else:
        os.environ["LICENSE_STORE_PATH"] = old


class TestLicenseService:
    def test_mint_and_verify(self, license_store):
        from services.license_service import LicenseService

        svc = LicenseService()
        info = svc.mint(holder="Acme Corp")
        assert info.key.startswith("VSK-")
        assert info.holder == "Acme Corp"

        out = svc.verify(info.key)
        assert out.key == info.key
        assert out.holder == "Acme Corp"

    def test_verify_invalid_key(self, license_store):
        from services.license_service import LicenseService
        from shared.digital_products import LicenseError

        svc = LicenseService()
        with pytest.raises(LicenseError):
            svc.verify("VSK-AAAA-BBBB-CCCC-DDDD")  # bad signature

    def test_list_and_stats(self, license_store):
        from services.license_service import LicenseService

        svc = LicenseService()
        svc.mint(holder="A")
        svc.mint(holder="B")
        assert svc.stats()["issued"] == 2
        assert svc.stats()["active"] == 2
        keys = svc.list_keys()
        assert len(keys) == 2

    def test_revoke(self, license_store):
        from services.license_service import LicenseService
        from shared.digital_products import LicenseError

        svc = LicenseService()
        info = svc.mint()
        assert svc.revoke(info.key) is True
        assert svc.revoke(info.key) is False  # already revoked -> not changed
        with pytest.raises(LicenseError):
            svc.verify_revoked(info.key)
        # unverified store path unaffected for non-revoked
        other = svc.mint(holder="Z")
        svc.verify(other.key)  # still valid


class TestLicenseRoutes:
    def test_mint_and_verify_api(self, client: TestClient, license_store):
        r = client.post("/api/v1/licenses/mint", json={"holder": "Acme Corp"})
        assert r.status_code == 201
        key = r.json()["key"]
        assert key.startswith("VSK-")

        r = client.post("/api/v1/licenses/verify", json={"key": key})
        assert r.status_code == 200
        assert r.json()["valid"] is True
        assert r.json()["holder"] == "Acme Corp"

        r = client.post("/api/v1/licenses/verify", json={"key": "VSK-BAD-SIGNATURE"})
        assert r.status_code == 400

    def test_get_and_list_api(self, client: TestClient, license_store):
        client.post("/api/v1/licenses/mint", json={"holder": "A"})
        client.post("/api/v1/licenses/mint", json={"holder": "B"})

        r = client.get("/api/v1/licenses")
        assert r.status_code == 200
        assert r.json()["stats"]["issued"] == 2
        assert len(r.json()["licenses"]) == 2

        key = r.json()["licenses"][0]["key"]
        r = client.get(f"/api/v1/licenses/{key}")
        assert r.status_code == 200
        assert r.json()["holder"] == "A"

        r = client.get("/api/v1/licenses/VSK-NONEXISTENT")
        assert r.status_code == 404

    def test_revoke_api(self, client: TestClient, license_store):
        r = client.post("/api/v1/licenses/mint", json={"holder": "Revokable"})
        key = r.json()["key"]

        r = client.post(f"/api/v1/licenses/{key}/revoke")
        assert r.status_code == 200
        assert r.json()["revoked"] is True

        r = client.post("/api/v1/licenses/verify", json={"key": key})
        assert r.status_code == 400


class TestLicenseMiddleware:
    """License-key middleware: /api/v1/licenses/validate requires X-License-Key."""

    def test_validate_requires_license(self, client: TestClient):
        r = client.get("/api/v1/licenses/validate")
        assert r.status_code == 401
        assert "license" in r.json()["detail"].lower()

    def test_validate_with_valid_license(self, client: TestClient, license_store):
        from services.license_service import LicenseService

        svc = LicenseService()
        info = svc.mint(holder="Acme Corp")

        r = client.get(
            "/api/v1/licenses/validate",
            headers={"X-License-Key": info.key},
        )
        assert r.status_code == 200, r.text
        assert r.json()["valid"] is True
        assert r.json()["holder"] == "Acme Corp"

    def test_validate_with_invalid_license(self, client: TestClient):
        r = client.get(
            "/api/v1/licenses/validate",
            headers={"X-License-Key": "VSK-BAD-SIGNATURE-KEY"},
        )
        assert r.status_code == 401

    def test_validate_with_revoked_license(self, client: TestClient, license_store):
        from services.license_service import LicenseService

        svc = LicenseService()
        info = svc.mint(holder="Revoked Corp")
        svc.revoke(info.key)

        r = client.get(
            "/api/v1/licenses/validate",
            headers={"X-License-Key": info.key},
        )
        assert r.status_code == 401

