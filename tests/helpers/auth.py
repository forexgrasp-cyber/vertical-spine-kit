# tests/helpers/auth.py
# Authentication helpers for tests.

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

TEST_PASSWORD = "Sup3rSecret!42"


def _register_and_capture_token(email: str, password: str = TEST_PASSWORD) -> dict:
    """Register user and return user_id + verification token (from dev log)."""
    with TestClient(app) as client:
        res = client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "auth_type": "jwt"},
        )
        assert res.status_code == 201, res.text
        data = res.json()
        return {"user_id": data["user_id"], "verification_token": data["verification_token"]}


def register_verify_login(email: str, password: str = TEST_PASSWORD) -> dict:
    """Register -> verify email -> login -> return tokens."""
    with TestClient(app) as client:
        reg_res = client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "auth_type": "jwt"},
        )
        assert reg_res.status_code == 201, reg_res.text
        reg_data = reg_res.json()
        token = reg_data["verification_token"]
        user_id = reg_data["user_id"]

        ver_res = client.post("/api/auth/verify-email", json={"token": token})
        assert ver_res.status_code == 200, ver_res.text
        assert ver_res.json()["status"] == "verified"

        login_res = client.post(
            "/api/auth/login",
            json={"email": email, "password": password, "auth_type": "jwt"},
        )
        assert login_res.status_code == 200, login_res.text
        tokens = login_res.json()
        assert tokens["access_token"]

        return {
            "user_id": user_id,
            "email": email,
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
        }


def make_authed_client() -> TestClient:
    """Create an authenticated TestClient."""
    import time
    email = f"test_{int(time.time())}@demo.example"
    auth = register_verify_login(email)
    client = TestClient(app)
    client.headers.update(auth["headers"])
    return client
