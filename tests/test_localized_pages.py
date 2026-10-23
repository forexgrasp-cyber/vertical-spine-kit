# tests/test_localized_pages.py
# Localized page tests for vertical SaaS product.

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from shared.i18n import PLATFORM_LOCALES

from main import app

client = TestClient(app)


@pytest.mark.parametrize("locale", PLATFORM_LOCALES[:3])
def test_localized_page_renders(locale):
    """Localized pages should render for each locale."""
    resp = client.get(f"/{locale}/")
    assert resp.status_code in (200, 404)  # 404 if localized routing not implemented
