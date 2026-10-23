# tests/test_openapi_api_key.py
# OpenAPI and API key tests for vertical SaaS product.

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_openapi_schema_accessible():
    """OpenAPI schema should be accessible."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert "openapi" in schema
    assert "paths" in schema


def test_docs_accessible():
    """Swagger UI should be accessible."""
    resp = client.get("/docs")
    assert resp.status_code == 200
