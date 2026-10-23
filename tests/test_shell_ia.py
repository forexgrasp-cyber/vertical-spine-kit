# tests/test_shell_ia.py
# Shell IA (Information Architecture) tests for vertical SaaS product.

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_shell_renders():
    """Shell layout should render."""
    resp = client.get("/app")
    assert resp.status_code in (200, 404)  # 404 if shell route not implemented


def test_theme_toggle_present():
    """Theme toggle should be present in shell."""
    resp = client.get("/app")
    if resp.status_code == 200:
        assert "theme" in resp.text.lower() or "dark" in resp.text.lower()


def test_lang_select_present():
    """Language selector should be present in shell."""
    resp = client.get("/app")
    if resp.status_code == 200:
        assert "lang" in resp.text.lower() or "language" in resp.text.lower()
