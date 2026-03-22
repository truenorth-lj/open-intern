"""Tests for admin/user management auth API."""

from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

# Set required env vars before importing
os.environ.setdefault("AUTH_SECRET", "test-secret-for-jwt-signing-1234567890abcdef")
os.environ.setdefault("DASHBOARD_PASSWORD", "admin-pass-123")
os.environ.setdefault("ADMIN_EMAIL", "admin@test.com")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://open_intern:open_intern@localhost:5556/open_intern"
)

from fastapi import FastAPI

import api.auth as auth_module
from api.auth import (
    _create_jwt,
    _decode_jwt,
    _generate_password,
    _hash_password,
    _verify_password,
    init_auth,
    router,
)

# Set JWT_SECRET for unit tests that don't go through init_auth
auth_module.JWT_SECRET = os.environ.get("AUTH_SECRET", "test-secret")

# --- Unit tests for auth utilities (no DB required) ---


class TestPasswordHashing:
    def test_hash_and_verify(self):
        password = "my-secret-pass"
        hashed = _hash_password(password)
        assert ":" in hashed
        assert _verify_password(password, hashed)

    def test_wrong_password_fails(self):
        hashed = _hash_password("correct-password")
        assert not _verify_password("wrong-password", hashed)

    def test_different_hashes_for_same_password(self):
        """Salt should make hashes unique."""
        h1 = _hash_password("same")
        h2 = _hash_password("same")
        assert h1 != h2
        assert _verify_password("same", h1)
        assert _verify_password("same", h2)


class TestPasswordGeneration:
    def test_generates_password(self):
        p = _generate_password()
        assert len(p) >= 12
        assert isinstance(p, str)

    def test_unique_passwords(self):
        passwords = {_generate_password() for _ in range(10)}
        assert len(passwords) == 10


class TestJWT:
    def test_create_and_decode(self):
        payload = {
            "user_id": "u1",
            "email": "a@b.com",
            "role": "admin",
            "exp": time.time() + 3600,
        }
        token = _create_jwt(payload)
        decoded = _decode_jwt(token)
        assert decoded is not None
        assert decoded["user_id"] == "u1"
        assert decoded["email"] == "a@b.com"
        assert decoded["role"] == "admin"

    def test_expired_token(self):
        payload = {"user_id": "u1", "exp": time.time() - 100}
        token = _create_jwt(payload)
        assert _decode_jwt(token) is None

    def test_invalid_token(self):
        assert _decode_jwt("invalid.token.here") is None
        assert _decode_jwt("") is None
        assert _decode_jwt("a.b") is None

    def test_tampered_token(self):
        payload = {"user_id": "u1", "exp": time.time() + 3600}
        token = _create_jwt(payload)
        parts = token.split(".")
        parts[1] = parts[1] + "x"
        tampered = ".".join(parts)
        assert _decode_jwt(tampered) is None


# --- Integration tests (require PostgreSQL) ---


def _check_db():
    """Return True if DB is available with users table."""
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        return False
    try:
        from sqlalchemy import create_engine, text

        sa_url = db_url
        if sa_url.startswith("postgresql+psycopg://"):
            sa_url = sa_url.replace("postgresql+psycopg://", "postgresql://", 1)
        engine = create_engine(sa_url)
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT EXISTS (SELECT FROM information_schema.tables "
                    "WHERE table_name = 'users')"
                )
            )
            return result.scalar()
    except Exception:
        return False


_db_available = _check_db()
requires_db = pytest.mark.skipif(not _db_available, reason="PostgreSQL not available")


def _cleanup_test_users():
    from sqlalchemy import create_engine, text

    db_url = os.environ["DATABASE_URL"]
    sa_url = db_url
    if sa_url.startswith("postgresql+psycopg://"):
        sa_url = sa_url.replace("postgresql+psycopg://", "postgresql://", 1)
    engine = create_engine(sa_url)
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM user_agent_access"))
        conn.execute(text("DELETE FROM users WHERE email LIKE '%@test-auth.com'"))
        conn.commit()


@pytest.fixture(scope="module")
def client():
    """Create test client with real database."""
    if not _db_available:
        pytest.skip("PostgreSQL not available")
    from core.config import AppConfig

    config = AppConfig()
    init_auth(config)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@requires_db
class TestLoginEndpoint:
    def setup_method(self):
        _cleanup_test_users()

    def test_admin_login(self, client):
        res = client.post(
            "/api/dashboard/auth/login",
            json={"email": "admin@test.com", "password": "admin-pass-123"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "token" in data
        assert data["user"]["role"] == "admin"
        assert data["user"]["email"] == "admin@test.com"

    def test_admin_wrong_password(self, client):
        res = client.post(
            "/api/dashboard/auth/login",
            json={"email": "admin@test.com", "password": "wrong"},
        )
        assert res.status_code == 401

    def test_nonexistent_user(self, client):
        res = client.post(
            "/api/dashboard/auth/login",
            json={"email": "nobody@test-auth.com", "password": "pass"},
        )
        assert res.status_code == 401


@requires_db
class TestMeEndpoint:
    def test_me_with_token(self, client):
        login_res = client.post(
            "/api/dashboard/auth/login",
            json={"email": "admin@test.com", "password": "admin-pass-123"},
        )
        token = login_res.json()["token"]
        res = client.get(
            "/api/dashboard/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        assert res.json()["role"] == "admin"

    def test_me_without_token(self, client):
        res = client.get("/api/dashboard/auth/me")
        assert res.status_code == 401


@requires_db
class TestUserManagement:
    def setup_method(self):
        _cleanup_test_users()

    def _admin_headers(self, client):
        res = client.post(
            "/api/dashboard/auth/login",
            json={"email": "admin@test.com", "password": "admin-pass-123"},
        )
        return {"Authorization": f"Bearer {res.json()['token']}"}

    def test_create_user(self, client):
        headers = self._admin_headers(client)
        res = client.post(
            "/api/dashboard/auth/users",
            json={"email": "new@test-auth.com"},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["email"] == "new@test-auth.com"
        assert "password" in data
        assert len(data["password"]) >= 12

    def test_create_duplicate_user(self, client):
        headers = self._admin_headers(client)
        client.post(
            "/api/dashboard/auth/users",
            json={"email": "dup@test-auth.com"},
            headers=headers,
        )
        res = client.post(
            "/api/dashboard/auth/users",
            json={"email": "dup@test-auth.com"},
            headers=headers,
        )
        assert res.status_code == 409

    def test_user_login_after_creation(self, client):
        headers = self._admin_headers(client)
        create_res = client.post(
            "/api/dashboard/auth/users",
            json={"email": "login@test-auth.com"},
            headers=headers,
        )
        password = create_res.json()["password"]
        login_res = client.post(
            "/api/dashboard/auth/login",
            json={"email": "login@test-auth.com", "password": password},
        )
        assert login_res.status_code == 200
        assert login_res.json()["user"]["role"] == "user"

    def test_list_users(self, client):
        headers = self._admin_headers(client)
        client.post(
            "/api/dashboard/auth/users",
            json={"email": "list@test-auth.com"},
            headers=headers,
        )
        res = client.get("/api/dashboard/auth/users", headers=headers)
        assert res.status_code == 200
        users = res.json()["users"]
        assert any(u["email"] == "list@test-auth.com" for u in users)

    def test_reset_password(self, client):
        headers = self._admin_headers(client)
        create_res = client.post(
            "/api/dashboard/auth/users",
            json={"email": "reset@test-auth.com"},
            headers=headers,
        )
        user_id = create_res.json()["user_id"]
        old_password = create_res.json()["password"]

        reset_res = client.post(
            f"/api/dashboard/auth/users/{user_id}/reset-password",
            headers=headers,
        )
        assert reset_res.status_code == 200
        new_password = reset_res.json()["password"]
        assert new_password != old_password

        # Old password should fail
        login_old = client.post(
            "/api/dashboard/auth/login",
            json={"email": "reset@test-auth.com", "password": old_password},
        )
        assert login_old.status_code == 401

        # New password should work
        login_new = client.post(
            "/api/dashboard/auth/login",
            json={"email": "reset@test-auth.com", "password": new_password},
        )
        assert login_new.status_code == 200

    def test_deactivate_user(self, client):
        headers = self._admin_headers(client)
        create_res = client.post(
            "/api/dashboard/auth/users",
            json={"email": "deact@test-auth.com"},
            headers=headers,
        )
        user_id = create_res.json()["user_id"]
        password = create_res.json()["password"]

        client.delete(f"/api/dashboard/auth/users/{user_id}", headers=headers)

        login_res = client.post(
            "/api/dashboard/auth/login",
            json={"email": "deact@test-auth.com", "password": password},
        )
        assert login_res.status_code == 401

    def test_user_cannot_access_admin_endpoints(self, client):
        headers = self._admin_headers(client)
        create_res = client.post(
            "/api/dashboard/auth/users",
            json={"email": "nonadmin@test-auth.com"},
            headers=headers,
        )
        password = create_res.json()["password"]

        login_res = client.post(
            "/api/dashboard/auth/login",
            json={"email": "nonadmin@test-auth.com", "password": password},
        )
        user_token = login_res.json()["token"]
        user_headers = {"Authorization": f"Bearer {user_token}"}

        res = client.get("/api/dashboard/auth/users", headers=user_headers)
        assert res.status_code == 403

    def test_agent_access(self, client):
        headers = self._admin_headers(client)
        create_res = client.post(
            "/api/dashboard/auth/users",
            json={"email": "access@test-auth.com", "agent_ids": ["agent1", "agent2"]},
            headers=headers,
        )
        user_id = create_res.json()["user_id"]

        res = client.get(f"/api/dashboard/auth/users/{user_id}/agents", headers=headers)
        assert res.status_code == 200
        assert set(res.json()["agent_ids"]) == {"agent1", "agent2"}

        res = client.put(
            f"/api/dashboard/auth/users/{user_id}/agents",
            json={"agent_ids": ["agent3"]},
            headers=headers,
        )
        assert res.status_code == 200

        res = client.get(f"/api/dashboard/auth/users/{user_id}/agents", headers=headers)
        assert res.json()["agent_ids"] == ["agent3"]
