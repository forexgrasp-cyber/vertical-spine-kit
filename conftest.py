"""Test environment for Vertical Spine Kit (no external services needed)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    from main import app

    return TestClient(app)
