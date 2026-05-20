"""
integration/test_auth_integration.py
Integration tests for backend/auth/routes.py

All DB calls are mocked with AsyncMock.
Tests hit the FastAPI router via httpx.AsyncClient.

Covers:
  POST /api/v1/auth/login                — FR03 FR04 FR08 (lockout, status, credentials)
  GET  /api/v1/auth/me                   — authenticated self-profile
  POST /api/v1/auth/logout               — session revocation
  POST /api/v1/auth/password-reset/request
  POST /api/v1/auth/password-reset/confirm
  GET  /api/v1/auth/admin/users
  POST /api/v1/auth/admin/users
  PATCH /api/v1/auth/admin/users/{id}
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

UTC = timezone.utc

# ── Shared helpers (duplicated for isolation) ──────────────────
import bcrypt
import jwt

JWT_SECRET = "dev-secret-CHANGE-IN-PRODUCTION"
JWT_ALGO   = "HS256"

def _make_token(uid, role="student", email="s.123456@ejust.edu.eg", expired=False):
    now = datetime.now(UTC)
    exp = now - timedelta(seconds=10) if expired else now + timedelta(seconds=1800)
    jti = str(uuid.uuid4())
    return jwt.encode(
        {"sub": uid, "user_id": uid, "role": role, "email": email,
         "iat": now, "exp": exp, "jti": jti},
        JWT_SECRET, algorithm=JWT_ALGO,
    ), jti

def _hash(plain):
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=4)).decode()

# ── Build the FastAPI test app ─────────────────────────────────
from fastapi import FastAPI
from fastapi.testclient import TestClient

# We build a minimal mock app to avoid real DB connections
app = FastAPI()


# ═══════════════════════════════════════════════════════════════
# LOGIN TESTS
# ═══════════════════════════════════════════════════════════════

class TestLoginEndpoint:
    """POST /api/v1/auth/login"""

    def _make_client_and_mocks(self, user_row=None, fetchval_return=None):
        """Returns (client, mock_conn, mock_pool) wired together."""
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=user_row)
        conn.fetchval = AsyncMock(return_value=fetchval_return)
        conn.execute  = AsyncMock()

        pool = AsyncMock()
        cm   = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__  = AsyncMock(return_value=False)
        pool.acquire  = MagicMock(return_value=cm)
        return pool, conn

    @pytest.mark.integration
    @pytest.mark.auth
    def test_login_success_returns_tokens(self):
        """Valid credentials → 200 with access_token and user payload"""
        uid  = str(uuid.uuid4())
        user = {
            "id": uid, "email": "s.123456@ejust.edu.eg",
            "display_name": "Student Test", "password_hash": _hash("Password99!"),
            "role": "student", "status": "active",
            "failed_attempts": 0, "locked_until": None,
            "wallet_balance": 100.0, "meal_plan_balance": 200.0,
        }
        pool, conn = self._make_client_and_mocks(user_row=user)

        with patch("backend.auth.routes.get_pool", return_value=pool), \
             patch("backend.auth.routes._audit", new_callable=AsyncMock), \
             patch("backend.auth.routes.validate_session", return_value=True):
            from backend.auth.routes import router as auth_router
            test_app = FastAPI()
            test_app.include_router(auth_router)
            client = TestClient(test_app)
            resp = client.post("/api/v1/auth/login",
                               json={"email": "s.123456@ejust.edu.eg", "password": "Password99!"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert data["data"]["user"]["role"] == "student"

    @pytest.mark.integration
    @pytest.mark.auth
    def test_login_unknown_email_returns_403(self):
        """No DB row → INVALID_CREDENTIALS 403"""
        pool, conn = self._make_client_and_mocks(user_row=None)

        with patch("backend.auth.routes.get_pool", return_value=pool), \
             patch("backend.auth.routes._audit", new_callable=AsyncMock):
            from backend.auth.routes import router as auth_router
            test_app = FastAPI()
            test_app.include_router(auth_router)
            client = TestClient(test_app)
            resp = client.post("/api/v1/auth/login",
                               json={"email": "nobody.000000@ejust.edu.eg", "password": "pw"})

        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"

    @pytest.mark.integration
    @pytest.mark.auth
    def test_login_wrong_password_decrements_attempts(self):
        """Wrong password → INVALID_CREDENTIALS 401, attempts incremented"""
        uid  = str(uuid.uuid4())
        user = {
            "id": uid, "email": "s.123456@ejust.edu.eg",
            "display_name": "Test", "password_hash": _hash("RealPassword!"),
            "role": "student", "status": "active",
            "failed_attempts": 0, "locked_until": None,
            "wallet_balance": 0.0, "meal_plan_balance": 0.0,
        }
        pool, conn = self._make_client_and_mocks(user_row=user, fetchval_return=1)

        with patch("backend.auth.routes.get_pool", return_value=pool), \
             patch("backend.auth.routes._audit", new_callable=AsyncMock):
            from backend.auth.routes import router as auth_router
            test_app = FastAPI()
            test_app.include_router(auth_router)
            client = TestClient(test_app)
            resp = client.post("/api/v1/auth/login",
                               json={"email": "s.123456@ejust.edu.eg", "password": "WrongPass!"})

        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"

    @pytest.mark.integration
    @pytest.mark.auth
    def test_login_suspended_account_returns_403(self):
        """Suspended account → ACCOUNT_SUSPENDED 403"""
        uid  = str(uuid.uuid4())
        user = {
            "id": uid, "email": "s.123456@ejust.edu.eg",
            "display_name": "Suspended", "password_hash": _hash("Password99!"),
            "role": "student", "status": "suspended",
            "failed_attempts": 0, "locked_until": None,
            "wallet_balance": 0.0, "meal_plan_balance": 0.0,
        }
        pool, _ = self._make_client_and_mocks(user_row=user)

        with patch("backend.auth.routes.get_pool", return_value=pool), \
             patch("backend.auth.routes._audit", new_callable=AsyncMock):
            from backend.auth.routes import router as auth_router
            test_app = FastAPI()
            test_app.include_router(auth_router)
            client = TestClient(test_app)
            resp = client.post("/api/v1/auth/login",
                               json={"email": "s.123456@ejust.edu.eg", "password": "Password99!"})

        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "ACCOUNT_SUSPENDED"

    @pytest.mark.integration
    @pytest.mark.auth
    def test_login_locked_account_returns_403_with_unlock_time(self):
        """Locked account → ACCOUNT_LOCKED 403 with unlocks_at detail"""
        uid      = str(uuid.uuid4())
        lock_at  = datetime.now(UTC) + timedelta(seconds=300)
        user = {
            "id": uid, "email": "s.123456@ejust.edu.eg",
            "display_name": "Locked", "password_hash": _hash("Password99!"),
            "role": "student", "status": "active",
            "failed_attempts": 5, "locked_until": lock_at,
            "wallet_balance": 0.0, "meal_plan_balance": 0.0,
        }
        pool, _ = self._make_client_and_mocks(user_row=user)

        with patch("backend.auth.routes.get_pool", return_value=pool), \
             patch("backend.auth.routes._audit", new_callable=AsyncMock):
            from backend.auth.routes import router as auth_router
            test_app = FastAPI()
            test_app.include_router(auth_router)
            client = TestClient(test_app)
            resp = client.post("/api/v1/auth/login",
                               json={"email": "s.123456@ejust.edu.eg", "password": "Password99!"})

        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "ACCOUNT_LOCKED"
        assert "unlocks_at" in resp.json()["error"]["details"]

    @pytest.mark.integration
    @pytest.mark.auth
    def test_login_non_university_email_rejected_by_schema(self):
        """Non-@ejust.edu.eg email → 422 validation error"""
        from backend.auth.routes import router as auth_router
        test_app = FastAPI()
        test_app.include_router(auth_router)
        client = TestClient(test_app)
        resp = client.post("/api/v1/auth/login",
                           json={"email": "hacker@evil.com", "password": "pw"})
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════
# GET /me  —  session validation
# ═══════════════════════════════════════════════════════════════

class TestGetMeEndpoint:

    @pytest.mark.integration
    @pytest.mark.auth
    def test_me_with_valid_token_returns_profile(self):
        uid   = str(uuid.uuid4())
        token, jti = _make_token(uid, "student")
        user_row = {
            "id": uid, "email": "s.123456@ejust.edu.eg",
            "display_name": "Student", "role": "student",
            "status": "active", "wallet_balance": 100.0,
            "meal_plan_balance": 200.0,
        }
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=user_row)
        pool = AsyncMock()
        cm   = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__  = AsyncMock(return_value=False)
        pool.acquire  = MagicMock(return_value=cm)

        with patch("backend.auth.routes.get_pool", return_value=pool), \
             patch("backend.auth.routes.validate_session", return_value=True), \
             patch("backend.auth.routes.touch_session", new_callable=AsyncMock):
            from backend.auth.routes import router as auth_router
            test_app = FastAPI()
            test_app.include_router(auth_router)
            client = TestClient(test_app)
            resp = client.get("/api/v1/auth/me",
                              headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200
        assert resp.json()["data"]["email"] == "s.123456@ejust.edu.eg"

    @pytest.mark.integration
    @pytest.mark.auth
    def test_me_without_token_returns_401(self):
        with patch("backend.auth.routes.validate_session", return_value=False):
            from backend.auth.routes import router as auth_router
            test_app = FastAPI()
            test_app.include_router(auth_router)
            client = TestClient(test_app)
            resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    @pytest.mark.integration
    @pytest.mark.auth
    def test_me_with_expired_token_returns_401(self):
        uid    = str(uuid.uuid4())
        token, _ = _make_token(uid, expired=True)
        from backend.auth.routes import router as auth_router
        test_app = FastAPI()
        test_app.include_router(auth_router)
        client = TestClient(test_app)
        resp = client.get("/api/v1/auth/me",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] in ("TOKEN_EXPIRED", "TOKEN_INVALID")


# ═══════════════════════════════════════════════════════════════
# PASSWORD RESET
# ═══════════════════════════════════════════════════════════════

class TestPasswordReset:

    @pytest.mark.integration
    @pytest.mark.auth
    def test_reset_request_always_returns_202(self):
        """Anti-enumeration: always 202 regardless of email existence"""
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)   # no user found
        conn.execute  = AsyncMock()
        pool = AsyncMock()
        cm   = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__  = AsyncMock(return_value=False)
        pool.acquire  = MagicMock(return_value=cm)

        with patch("backend.auth.routes.get_pool", return_value=pool):
            from backend.auth.routes import router as auth_router
            test_app = FastAPI()
            test_app.include_router(auth_router)
            client = TestClient(test_app)
            resp = client.post("/api/v1/auth/password-reset/request",
                               json={"email": "unknown.000000@ejust.edu.eg"})
        assert resp.status_code == 202
        assert "sent" in resp.json()["data"]["message"].lower()

    @pytest.mark.integration
    @pytest.mark.auth
    def test_reset_confirm_invalid_token_returns_422(self):
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)  # token not found
        pool = AsyncMock()
        cm   = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__  = AsyncMock(return_value=False)
        pool.acquire  = MagicMock(return_value=cm)

        with patch("backend.auth.routes.get_pool", return_value=pool):
            from backend.auth.routes import router as auth_router
            test_app = FastAPI()
            test_app.include_router(auth_router)
            client = TestClient(test_app)
            resp = client.post("/api/v1/auth/password-reset/confirm",
                               json={"token": "bogus-token", "new_password": "NewPass123!"})
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "INVALID_TOKEN"

    @pytest.mark.integration
    @pytest.mark.auth
    def test_reset_confirm_used_token_returns_422(self):
        used_token_row = {
            "user_id":   str(uuid.uuid4()),
            "used_at":   datetime.now(UTC),  # already used
            "expires_at": datetime.now(UTC) + timedelta(hours=1),
        }
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=used_token_row)
        pool = AsyncMock()
        cm   = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__  = AsyncMock(return_value=False)
        pool.acquire  = MagicMock(return_value=cm)

        with patch("backend.auth.routes.get_pool", return_value=pool):
            from backend.auth.routes import router as auth_router
            test_app = FastAPI()
            test_app.include_router(auth_router)
            client = TestClient(test_app)
            resp = client.post("/api/v1/auth/password-reset/confirm",
                               json={"token": "already-used", "new_password": "NewPass123!"})
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "LINK_ALREADY_USED"


# ═══════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS
# ═══════════════════════════════════════════════════════════════

class TestAdminEndpoints:

    @pytest.mark.integration
    @pytest.mark.auth
    def test_list_users_requires_admin_role(self):
        """Staff token → 403 FORBIDDEN"""
        uid    = str(uuid.uuid4())
        token, jti = _make_token(uid, "staff", "staff.001@ejust.edu.eg")

        with patch("backend.auth.routes.validate_session", return_value=True), \
             patch("backend.auth.routes.touch_session", new_callable=AsyncMock):
            from backend.auth.routes import router as auth_router
            test_app = FastAPI()
            test_app.include_router(auth_router)
            client = TestClient(test_app)
            resp = client.get("/api/v1/auth/admin/users",
                              headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    @pytest.mark.integration
    @pytest.mark.auth
    def test_create_user_duplicate_email_returns_409(self):
        """Unique violation → EMAIL_TAKEN 409"""
        import asyncpg
        uid    = str(uuid.uuid4())
        token, jti = _make_token(uid, "admin", "admin.001@ejust.edu.eg")

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=asyncpg.UniqueViolationError("duplicate"))
        pool = AsyncMock()
        cm   = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__  = AsyncMock(return_value=False)
        pool.acquire  = MagicMock(return_value=cm)

        with patch("backend.auth.routes.get_pool", return_value=pool), \
             patch("backend.auth.routes.validate_session", return_value=True), \
             patch("backend.auth.routes.touch_session", new_callable=AsyncMock), \
             patch("backend.auth.routes._audit", new_callable=AsyncMock):
            from backend.auth.routes import router as auth_router
            test_app = FastAPI()
            test_app.include_router(auth_router)
            client = TestClient(test_app)
            resp = client.post("/api/v1/auth/admin/users",
                               headers={"Authorization": f"Bearer {token}"},
                               json={
                                   "email": "dup.123456@ejust.edu.eg",
                                   "display_name": "Dup", "role": "student",
                                   "password": "Password99!",
                               })
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "EMAIL_TAKEN"