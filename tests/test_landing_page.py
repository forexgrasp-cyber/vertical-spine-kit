# tests/test_landing_page.py
# Landing page tests for vertical SaaS product.

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_landing_page_loads():
    """Landing page should load successfully."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "html" in resp.headers.get("content-type", "").lower()


def test_landing_page_has_seo_meta():
    """Landing page should have SEO meta tags."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<title>" in resp.text
    assert "description" in resp.text.lower()
