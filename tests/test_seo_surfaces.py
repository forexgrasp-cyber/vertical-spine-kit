# tests/test_seo_surfaces.py
# SEO surface tests for vertical SaaS product.

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_sitemap_xml():
    """Sitemap should be accessible and valid XML."""
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert "xml" in resp.headers.get("content-type", "").lower()
    assert "<urlset" in resp.text


def test_robots_txt():
    """Robots.txt should be accessible."""
    resp = client.get("/robots.txt")
    assert resp.status_code == 200
    assert "User-agent" in resp.text


def test_seo_manifest():
    """SEO manifest should be accessible."""
    resp = client.get("/api/seo/manifest")
    assert resp.status_code == 200
    data = resp.json()
    assert "vertical_id" in data
    assert "product" in data
    assert "surfaces" in data


def test_design_tokens_css():
    """Design tokens CSS should be accessible."""
    resp = client.get("/api/seo/style/tokens.css")
    assert resp.status_code == 200
    assert "css" in resp.headers.get("content-type", "").lower()
    assert ":root" in resp.text
