# tests/test_api.py
# API endpoint tests for vertical SaaS product.

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture(scope="session")
def client():
    """Create a test client."""
    return TestClient(app)


def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_seo_surfaces_accessible(client):
    """SEO surfaces should be accessible without auth."""
    resp = client.get("/api/seo/manifest")
    assert resp.status_code == 200

    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200

    resp = client.get("/robots.txt")
    assert resp.status_code == 200

    resp = client.get("/api/seo/style/tokens.css")
    assert resp.status_code == 200
    assert ":root" in resp.text


def test_i18n_languages_endpoint(client):
    """i18n languages endpoint should return all 20 platform locales."""
    from shared.i18n import PLATFORM_LOCALES
    resp = client.get("/api/i18n/languages")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data["languages"]) == set(PLATFORM_LOCALES)
    assert data["dirs"]["ar"] == "rtl"
    assert data["dirs"]["fa"] == "rtl"


def test_metrics_endpoint_requires_auth(client):
    """Metrics endpoint should require authentication."""
    resp = client.get("/api/v1/metrics")
    assert resp.status_code == 401
