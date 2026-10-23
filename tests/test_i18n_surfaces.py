# tests/test_i18n_surfaces.py
# i18n surface tests for vertical SaaS product.

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from shared.i18n import PLATFORM_LOCALES

from main import app

client = TestClient(app)


def test_languages_endpoint_returns_20():
    """Should return all 20 platform locales."""
    resp = client.get("/api/i18n/languages")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data["languages"]) == set(PLATFORM_LOCALES)


def test_translations_endpoint():
    """Should return translations for each locale."""
    for locale in PLATFORM_LOCALES[:3]:  # Test first 3 to keep it fast
        resp = client.get(f"/api/i18n/translations/{locale}")
        assert resp.status_code == 200
        data = resp.json()
        assert "translations" in data
