"""
conftest.py  — root-level shared fixtures
Provides: mock DB pool, JWT helpers, fake user factory, test client
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import bcrypt
import jwt
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

# ── Constants matching production config ──────────────────────
JWT_SECRET = "dev-secret-CHANGE-IN-PRODUCTION"
JWT_ALGO   = "HS256"
UTC        = timezone.utc

# ── JWT helpers ───────────────────────────────────────────────

def make_jwt(user_id: str, role: str = "student", email: str = "test.123456@ejust.edu.eg",
             expired: bool = False) -> str:
    now = datetime.now(UTC)
    exp = now - timedelta(seconds=10) if expired else now + timedelta(seconds=1800)
    return jwt.encode(
        {"sub": user_id, "user_id": user_id, "role": role,
         "email": email, "iat": now, "exp": exp, "jti": str(uuid.uuid4())},
        JWT_SECRET, algorithm=JWT_ALGO,
    )


def hash_pw(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=4)).decode()


# ── Fake data factories ───────────────────────────────────────

def fake_user(role: str = "student", status: str = "active", **overrides) -> dict:
    uid = str(uuid.uuid4())
    base = {
        "id":                uid,
        "email":             "student.123456@ejust.edu.eg",
        "display_name":      "Test Student",
        "password_hash":     hash_pw("Password123!"),
        "role":              role,
        "status":            status,
        "failed_attempts":   0,
        "locked_until":      None,
        "wallet_balance":    100.00,
        "meal_plan_balance": 200.00,
    }
    base.update(overrides)
    return base


def fake_menu_item(**overrides) -> dict:
    base = {
        "id":            1,
        "name":          "Grilled Chicken Bowl",
        "category":      "meals",
        "price":         45.00,
        "stock_qty":     20,
        "max_order_qty": 5,
        "active":        True,
    }
    base.update(overrides)
    return base


def fake_order(user_id: str = None, **overrides) -> dict:
    oid = str(uuid.uuid4())
    base = {
        "id":               oid,
        "user_id":          user_id or str(uuid.uuid4()),
        "status":           "pending_payment",
        "subtotal":         45.00,
        "discount":         0.00,
        "total":            45.00,
        "voucher_code":     None,
        "voucher_id":       None,
        "notes":            "",
        "payment_method":   None,
        "idempotency_key":  f"IDP-{uuid.uuid4().hex}",
        "created_at":       datetime.now(UTC),
        "confirmed_at":     None,
        "cancelled_at":     None,
    }
    base.update(overrides)
    return base


def fake_voucher(**overrides) -> dict:
    base = {
        "id":           str(uuid.uuid4()),
        "code":         "SAVE20",
        "discount":     20.00,
        "discount_type": "flat",
        "discount_value": 20.00,
        "min_order":    50.00,
        "used_by":      None,
        "is_active":    True,
        "expires_at":   datetime.now(UTC) + timedelta(days=30),
    }
    base.update(overrides)
    return base


# ── Mock asyncpg connection ───────────────────────────────────

def make_mock_conn(fetchrow_return=None, fetch_return=None,
                   fetchval_return=None, execute_return=None):
    """Build a re-usable async context-manager mock for asyncpg connections."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.fetch    = AsyncMock(return_value=fetch_return or [])
    conn.fetchval = AsyncMock(return_value=fetchval_return)
    conn.execute  = AsyncMock(return_value=execute_return)

    pool = AsyncMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__  = AsyncMock(return_value=False)
    return pool, conn


# ── Shared fixtures ───────────────────────────────────────────

@pytest.fixture
def student_token():
    uid = str(uuid.uuid4())
    return make_jwt(uid, "student"), uid


@pytest.fixture
def staff_token():
    uid = str(uuid.uuid4())
    return make_jwt(uid, "staff", "staff.001@ejust.edu.eg"), uid


@pytest.fixture
def admin_token():
    uid = str(uuid.uuid4())
    return make_jwt(uid, "admin", "admin.001@ejust.edu.eg"), uid


@pytest.fixture
def expired_token():
    uid = str(uuid.uuid4())
    return make_jwt(uid, "student", expired=True), uid


@pytest.fixture
def sample_user():
    return fake_user()


@pytest.fixture
def sample_menu_item():
    return fake_menu_item()


@pytest.fixture
def sample_order(sample_user):
    return fake_order(user_id=sample_user["id"])


@pytest.fixture
def sample_voucher():
    return fake_voucher()