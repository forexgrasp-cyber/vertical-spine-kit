"""Test environment for Vertical Spine Kit (no external services needed)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT.parent / "shared-canonical-services"):
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))


@pytest.fixture()
def client() -> TestClient:
    from main import app

    return TestClient(app)
