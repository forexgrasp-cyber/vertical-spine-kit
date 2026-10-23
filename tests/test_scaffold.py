"""Scaffold smoke tests: platform surfaces + design conformance."""

from __future__ import annotations

from fastapi.testclient import TestClient
from shared.i18n import PLATFORM_LOCALES

from main import app

client = TestClient(app)


def test_health() -> None:
    assert client.get("/api/health").json()["status"] == "healthy"


def test_seo_surfaces() -> None:
    assert client.get("/api/seo/manifest").status_code == 200
    assert client.get("/sitemap.xml").status_code == 200
    assert client.get("/robots.txt").status_code == 200
    tokens = client.get("/api/seo/style/tokens.css")
    assert tokens.status_code == 200
    assert ":root" in tokens.text


def test_languages_are_platform_twenty() -> None:
    data = client.get("/api/i18n/languages").json()
    assert set(data["languages"]) == set(PLATFORM_LOCALES)
    assert data["dirs"]["ar"] == "rtl"
    assert data["dirs"]["fa"] == "rtl"


def test_design_conformance_passes() -> None:
    from shared.webui.design_conformance import audit_product

    def fetch(url: str) -> tuple[int, dict, str]:
        resp = client.get(url)
        return resp.status_code, dict(resp.headers), resp.text

    result = audit_product("vertical-spine-kit", "http://test", fetch=fetch)
    assert result.ok, [f"{c.name}: {c.detail}" for c in result.failures()]
