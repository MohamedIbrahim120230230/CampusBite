"""
integration/test_order_integration.py
Integration tests for backend/order/order_payment.py

DB is mocked via psycopg2 patch. Tests hit FastAPI routes.

Covers:
  POST /api/v1/orders               — place order (FR22 oversell, idempotency, load-shed)
  GET  /api/v1/orders/{id}
  POST /api/v1/orders/{id}/cancel   — cancellation window logic
  POST /api/v1/payments/process     — cash / online / wallet / meal_plan
  POST /api/v1/payments/{id}/callback
  POST /api/v1/payments/{id}/retry  — max 4 attempts
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import bcrypt
import jwt
import pytest

UTC        = timezone.utc
JWT_SECRET = "dev-secret-CHANGE-IN-PRODUCTION"
JWT_ALGO   = "HS256"


def _make_token(uid, role="student", email="s.123456@ejust.edu.eg"):
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": uid, "user_id": uid, "role": role, "email": email,
         "iat": now, "exp": now + timedelta(seconds=1800),
         "jti": str(uuid.uuid4())},
        JWT_SECRET, algorithm=JWT_ALGO,
    )


def _make_psycopg2_cursor(fetchone_ret=None, fetchall_ret=None, fetchval_ret=None):
    """Mock psycopg2 cursor (RealDictCursor style)."""
    cur = MagicMock()
    cur.fetchone    = MagicMock(return_value=fetchone_ret)
    cur.fetchall    = MagicMock(return_value=fetchall_ret or [])
    cur.__enter__   = MagicMock(return_value=cur)
    cur.__exit__    = MagicMock(return_value=False)
    return cur


def _make_psycopg2_conn(cursor):
    conn = MagicMock()
    conn.cursor  = MagicMock(return_value=cursor)
    conn.commit  = MagicMock()
    conn.rollback= MagicMock()
    conn.close   = MagicMock()
    return conn


# ── FastAPI test client factory ───────────────────────────────
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_test_client():
    from backend.order.order_payment import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


# ═══════════════════════════════════════════════════════════════
# PLACE ORDER
# ═══════════════════════════════════════════════════════════════

class TestPlaceOrder:
    """POST /api/v1/orders"""

    @pytest.mark.integration
    @pytest.mark.order
    def test_no_auth_returns_401(self):
        client = _make_test_client()
        resp   = client.post("/api/v1/orders", json={"items": []})
        assert resp.status_code == 401

    @pytest.mark.integration
    @pytest.mark.order
    def test_empty_cart_returns_400(self):
        uid   = str(uuid.uuid4())
        token = _make_token(uid)
        cur   = _make_psycopg2_cursor(
            fetchone_ret=None,  # no idempotency match
        )
        cur.fetchone = MagicMock(side_effect=[
            None,                                    # idempotency check
            {"count": 0},                            # concurrency check
            None,                                    # cart session empty
        ])
        conn = _make_psycopg2_conn(cur)

        with patch("backend.order.order_payment.get_db", return_value=conn):
            resp = TestClient(_make_test_client().app).post(
                "/api/v1/orders",
                headers={"Authorization": f"Bearer {token}"},
                json={"items": []},
            )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "EMPTY_CART"

    @pytest.mark.integration
    @pytest.mark.order
    def test_oversell_prevention_returns_409(self):
        """Stock qty < requested → OVERSELL_PREVENTED 409"""
        uid   = str(uuid.uuid4())
        token = _make_token(uid)

        # Sequence of fetchone calls:
        # 1. idempotency check → None
        # 2. concurrency check → {"count": 0}
        # 3. menu item FOR UPDATE → item with stock_qty 0
        item = {"id": 1, "name": "Chicken Bowl", "price": 45.00,
                "stock_qty": 0, "active": True}
        cur = _make_psycopg2_cursor()
        cur.fetchone = MagicMock(side_effect=[
            None,          # idempotency
            {"count": 0},  # concurrency
            item,          # menu item
        ])
        conn = _make_psycopg2_conn(cur)

        with patch("backend.order.order_payment.get_db", return_value=conn):
            client = TestClient(_make_test_client().app)
            resp = client.post(
                "/api/v1/orders",
                headers={"Authorization": f"Bearer {token}"},
                json={"items": [{"menu_item_id": 1, "quantity": 2}]},
            )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "OVERSELL_PREVENTED"

    @pytest.mark.integration
    @pytest.mark.order
    def test_system_overloaded_returns_503(self):
        """Active orders >= 150 → SYSTEM_OVERLOADED 503"""
        uid   = str(uuid.uuid4())
        token = _make_token(uid)
        cur   = _make_psycopg2_cursor()
        cur.fetchone = MagicMock(side_effect=[
            None,              # idempotency
            {"count": 150},    # concurrency at limit
        ])
        conn = _make_psycopg2_conn(cur)

        with patch("backend.order.order_payment.get_db", return_value=conn):
            client = TestClient(_make_test_client().app)
            resp = client.post(
                "/api/v1/orders",
                headers={"Authorization": f"Bearer {token}"},
                json={"items": [{"menu_item_id": 1, "quantity": 1}]},
            )
        assert resp.status_code == 503
        assert resp.json()["detail"]["code"] == "SYSTEM_OVERLOADED"

    @pytest.mark.integration
    @pytest.mark.order
    def test_idempotent_duplicate_returns_existing_order(self):
        """Duplicate idempotency key within window → return existing order"""
        uid   = str(uuid.uuid4())
        token = _make_token(uid)
        oid   = str(uuid.uuid4())
        existing_order = {
            "id": oid, "status": "pending_payment",
            "total": 45.0, "subtotal": 45.0, "discount": 0.0,
            "voucher_code": None, "created_at": datetime.now(UTC),
        }
        cur = _make_psycopg2_cursor(fetchone_ret=existing_order, fetchall_ret=[])
        conn = _make_psycopg2_conn(cur)

        with patch("backend.order.order_payment.get_db", return_value=conn):
            client = TestClient(_make_test_client().app)
            resp = client.post(
                "/api/v1/orders",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "idempotency_key": "IDP-same-key",
                    "items": [{"menu_item_id": 1, "quantity": 1}],
                },
            )
        assert resp.status_code == 200
        assert resp.json()["duplicate"] is True


# ═══════════════════════════════════════════════════════════════
# GET ORDER
# ═══════════════════════════════════════════════════════════════

class TestGetOrder:

    @pytest.mark.integration
    @pytest.mark.order
    def test_get_existing_order(self):
        oid   = str(uuid.uuid4())
        order = {
            "id": oid, "status": "confirmed", "total": 45.0,
            "subtotal": 45.0, "discount": 0.0, "created_at": datetime.now(UTC),
            "confirmed_at": None, "cancelled_at": None,
            "payment_method": None, "notes": "", "user_id": str(uuid.uuid4()),
            "voucher_code": None, "voucher_id": None,
            "idempotency_key": "IDP-x",
        }
        cur = _make_psycopg2_cursor(fetchone_ret=order, fetchall_ret=[])
        conn = _make_psycopg2_conn(cur)

        with patch("backend.order.order_payment.get_db", return_value=conn):
            client = TestClient(_make_test_client().app)
            resp = client.get(f"/api/v1/orders/{oid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"

    @pytest.mark.integration
    @pytest.mark.order
    def test_get_nonexistent_order_returns_404(self):
        cur  = _make_psycopg2_cursor(fetchone_ret=None)
        conn = _make_psycopg2_conn(cur)
        with patch("backend.order.order_payment.get_db", return_value=conn):
            client = TestClient(_make_test_client().app)
            resp = client.get(f"/api/v1/orders/{uuid.uuid4()}")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# CANCEL ORDER
# ═══════════════════════════════════════════════════════════════

class TestCancelOrder:

    @pytest.mark.integration
    @pytest.mark.order
    def test_cancel_pending_payment_order_succeeds(self):
        oid   = str(uuid.uuid4())
        order = {
            "id": oid, "status": "pending_payment", "total": 45.0,
            "payment_method": "cash", "confirmed_at": None,
        }
        cur = _make_psycopg2_cursor(fetchone_ret=order)
        cur.fetchall = MagicMock(return_value=[])
        conn = _make_psycopg2_conn(cur)

        with patch("backend.order.order_payment.get_db", return_value=conn):
            client = TestClient(_make_test_client().app)
            resp = client.post(f"/api/v1/orders/{oid}/cancel")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.integration
    @pytest.mark.order
    def test_cancel_completed_order_returns_409(self):
        oid   = str(uuid.uuid4())
        order = {"id": oid, "status": "completed", "total": 45.0,
                 "payment_method": "cash", "confirmed_at": None}
        cur  = _make_psycopg2_cursor(fetchone_ret=order)
        conn = _make_psycopg2_conn(cur)

        with patch("backend.order.order_payment.get_db", return_value=conn):
            client = TestClient(_make_test_client().app)
            resp = client.post(f"/api/v1/orders/{oid}/cancel")
        assert resp.status_code == 409

    @pytest.mark.integration
    @pytest.mark.order
    def test_cancel_confirmed_outside_window_shows_partial_refund_message(self):
        oid          = str(uuid.uuid4())
        confirmed_at = datetime.now(UTC) - timedelta(minutes=20)  # past window
        order = {
            "id": oid, "status": "confirmed", "total": 45.0,
            "payment_method": "online",
            "confirmed_at": confirmed_at.replace(tzinfo=None),
        }
        cur  = _make_psycopg2_cursor(fetchone_ret=order)
        conn = _make_psycopg2_conn(cur)

        with patch("backend.order.order_payment.get_db", return_value=conn):
            client = TestClient(_make_test_client().app)
            resp = client.post(f"/api/v1/orders/{oid}/cancel")
        data = resp.json()
        assert data.get("success") is False
        assert data.get("code") == "CANCELLATION_WINDOW_EXPIRED"


# ═══════════════════════════════════════════════════════════════
# PAYMENT PROCESSING
# ═══════════════════════════════════════════════════════════════

class TestPaymentProcessing:

    def _order_row(self, oid, status="pending_payment", pm=None):
        return {
            "id": oid, "status": status, "total": 45.0,
            "payment_method": pm, "user_id": str(uuid.uuid4()),
        }

    @pytest.mark.integration
    @pytest.mark.order
    def test_cash_payment_confirms_order(self):
        oid = str(uuid.uuid4())
        pid = str(uuid.uuid4())
        order = self._order_row(oid)
        cur = _make_psycopg2_cursor(fetchone_ret=order)
        cur.fetchone = MagicMock(side_effect=[order, None])
        conn = _make_psycopg2_conn(cur)

        with patch("backend.order.order_payment.get_db", return_value=conn), \
             patch("backend.order.order_payment.gen_uuid", return_value=pid):
            client = TestClient(_make_test_client().app)
            resp = client.post("/api/v1/payments/process",
                               json={"order_id": oid, "payment_method": "cash"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data.get("order_status") == "confirmed"

    @pytest.mark.integration
    @pytest.mark.order
    def test_online_payment_stays_pending(self):
        """Online payment stays pending until callback."""
        oid   = str(uuid.uuid4())
        pid   = str(uuid.uuid4())
        order = self._order_row(oid)
        cur   = _make_psycopg2_cursor(fetchone_ret=order)
        conn  = _make_psycopg2_conn(cur)

        with patch("backend.order.order_payment.get_db", return_value=conn), \
             patch("backend.order.order_payment.gen_uuid", return_value=pid):
            client = TestClient(_make_test_client().app)
            resp = client.post("/api/v1/payments/process",
                               json={"order_id": oid, "payment_method": "online"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "payment_id" in data
        # Online should NOT immediately confirm
        assert data.get("order_status") != "confirmed"

    @pytest.mark.integration
    @pytest.mark.order
    def test_payment_callback_success_confirms_order(self):
        pid   = str(uuid.uuid4())
        oid   = str(uuid.uuid4())
        payment = {"id": pid, "order_id": oid, "status": "pending",
                   "amount": 45.0, "method": "online"}
        cur  = _make_psycopg2_cursor(fetchone_ret=payment)
        conn = _make_psycopg2_conn(cur)

        with patch("backend.order.order_payment.get_db", return_value=conn):
            client = TestClient(_make_test_client().app)
            resp = client.post(f"/api/v1/payments/{pid}/callback",
                               json={"success": True, "transaction_id": "TXN-123"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["order_status"] == "confirmed"

    @pytest.mark.integration
    @pytest.mark.order
    def test_payment_callback_failure_records_reason(self):
        pid     = str(uuid.uuid4())
        oid     = str(uuid.uuid4())
        payment = {"id": pid, "order_id": oid, "status": "pending",
                   "amount": 45.0, "method": "online"}
        cur  = _make_psycopg2_cursor(fetchone_ret=payment)
        conn = _make_psycopg2_conn(cur)

        with patch("backend.order.order_payment.get_db", return_value=conn):
            client = TestClient(_make_test_client().app)
            resp = client.post(f"/api/v1/payments/{pid}/callback",
                               json={"success": False, "failure_reason": "insufficient_funds"})
        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert resp.json()["failure_reason"] == "insufficient_funds"

    @pytest.mark.integration
    @pytest.mark.order
    def test_payment_retry_max_attempts_returns_409(self):
        """4 existing payments → MAX_RETRIES_EXCEEDED"""
        pid     = str(uuid.uuid4())
        payment = {"id": pid, "order_id": str(uuid.uuid4()),
                   "status": "failed", "amount": 45.0, "method": "online"}
        cur = _make_psycopg2_cursor()
        cur.fetchone = MagicMock(side_effect=[
            payment,        # payment lookup
            {"cnt": 4},     # count of existing payments
        ])
        conn = _make_psycopg2_conn(cur)

        with patch("backend.order.order_payment.get_db", return_value=conn):
            client = TestClient(_make_test_client().app)
            resp = client.post(f"/api/v1/payments/{pid}/retry")
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "MAX_RETRIES_EXCEEDED"

    @pytest.mark.integration
    @pytest.mark.order
    def test_order_not_awaiting_payment_returns_409(self):
        """Order already confirmed → 409"""
        oid   = str(uuid.uuid4())
        order = self._order_row(oid, status="confirmed")
        cur   = _make_psycopg2_cursor(fetchone_ret=order)
        conn  = _make_psycopg2_conn(cur)

        with patch("backend.order.order_payment.get_db", return_value=conn):
            client = TestClient(_make_test_client().app)
            resp = client.post("/api/v1/payments/process",
                               json={"order_id": oid, "payment_method": "cash"})
        assert resp.status_code == 409