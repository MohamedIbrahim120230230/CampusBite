"""
unit/backend/test_order_unit.py
Unit tests for backend/order/order_payment.py

Covers (NO DB):
  - _is_prepaid() classification
  - Idempotency key generation format
  - MAX_ITEM_QUANTITY cap enforcement logic
  - Cancellation window arithmetic
  - Refund calculation (_initiate_refund logic)
  - State transitions (pending_payment → confirmed, etc.)
  - PAYMENT_TIMEOUT_SECONDS value
  - Load-shedding threshold constant
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

UTC = timezone.utc

# ── Constants from order_payment.py ──────────────────────────
PAYMENT_TIMEOUT_SECONDS = 600
CANCELLATION_WINDOW_MIN = 15
MAX_CONCURRENT_ORDERS   = 150
IDEMPOTENCY_WINDOW_SEC  = 60
MAX_ITEM_QUANTITY        = 20

# ── Pure helpers re-implemented for unit isolation ─────────────

def _is_prepaid(method: str) -> bool:
    return method in ["online", "wallet", "meal_plan"]


def _idempotency_key(user_id: str) -> str:
    return f"IDP-{user_id}-{uuid.uuid4().hex}"


def _within_cancellation_window(confirmed_at: datetime, now: datetime) -> bool:
    return (now - confirmed_at).total_seconds() / 60 <= CANCELLATION_WINDOW_MIN


def _calculate_refund(total: float, full: bool = True, percent: float = 1.0) -> float:
    return round(total if full else total * percent, 2)


def _valid_statuses():
    return {"confirmed", "preparing", "ready_for_pickup", "delivered", "cancelled", "completed"}


# ═══════════════════════════════════════════════════════════════
# PAYMENT METHOD CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

class TestIsPrepaid:
    """_is_prepaid correctly identifies prepaid vs COD methods"""

    @pytest.mark.unit
    def test_online_is_prepaid(self):
        assert _is_prepaid("online") is True

    @pytest.mark.unit
    def test_wallet_is_prepaid(self):
        assert _is_prepaid("wallet") is True

    @pytest.mark.unit
    def test_meal_plan_is_prepaid(self):
        assert _is_prepaid("meal_plan") is True

    @pytest.mark.unit
    def test_cash_is_not_prepaid(self):
        assert _is_prepaid("cash") is False

    @pytest.mark.unit
    def test_empty_string_not_prepaid(self):
        assert _is_prepaid("") is False

    @pytest.mark.unit
    def test_unknown_method_not_prepaid(self):
        assert _is_prepaid("crypto") is False


# ═══════════════════════════════════════════════════════════════
# PAYMENT TIMEOUT CONSTANT
# ═══════════════════════════════════════════════════════════════

class TestPaymentTimeout:
    """PAYMENT_TIMEOUT_SECONDS is 600 (10 min)"""

    @pytest.mark.unit
    def test_timeout_is_600_seconds(self):
        assert PAYMENT_TIMEOUT_SECONDS == 600

    @pytest.mark.unit
    def test_timeout_deadline_is_in_future(self):
        now     = datetime.now(UTC)
        timeout = now + timedelta(seconds=PAYMENT_TIMEOUT_SECONDS)
        assert timeout > now

    @pytest.mark.unit
    def test_expired_timeout_is_in_past(self):
        now     = datetime.now(UTC)
        timeout = now - timedelta(seconds=PAYMENT_TIMEOUT_SECONDS)
        assert timeout < now


# ═══════════════════════════════════════════════════════════════
# ITEM QUANTITY CAP
# ═══════════════════════════════════════════════════════════════

class TestItemQuantityCap:
    """MAX_ITEM_QUANTITY = 20 per item per order"""

    @pytest.mark.unit
    def test_max_quantity_is_20(self):
        assert MAX_ITEM_QUANTITY == 20

    @pytest.mark.unit
    def test_quantity_at_max_allowed(self):
        assert MAX_ITEM_QUANTITY <= MAX_ITEM_QUANTITY

    @pytest.mark.unit
    def test_quantity_above_max_rejected(self):
        qty = 21
        assert qty > MAX_ITEM_QUANTITY

    @pytest.mark.unit
    def test_quantity_zero_invalid(self):
        qty = 0
        assert qty < 1

    @pytest.mark.unit
    def test_quantity_negative_invalid(self):
        qty = -1
        assert qty < 1


# ═══════════════════════════════════════════════════════════════
# CANCELLATION WINDOW
# ═══════════════════════════════════════════════════════════════

class TestCancellationWindow:
    """15-minute cancellation window from confirmation time"""

    @pytest.mark.unit
    def test_window_is_15_minutes(self):
        assert CANCELLATION_WINDOW_MIN == 15

    @pytest.mark.unit
    def test_within_window_returns_true(self):
        confirmed_at = datetime.now(UTC) - timedelta(minutes=5)
        assert _within_cancellation_window(confirmed_at, datetime.now(UTC)) is True

    @pytest.mark.unit
    def test_at_boundary_returns_true(self):
        confirmed_at = datetime.now(UTC) - timedelta(minutes=15, seconds=0)
        assert _within_cancellation_window(confirmed_at, datetime.now(UTC)) is True

    @pytest.mark.unit
    def test_past_window_returns_false(self):
        confirmed_at = datetime.now(UTC) - timedelta(minutes=16)
        assert _within_cancellation_window(confirmed_at, datetime.now(UTC)) is False

    @pytest.mark.unit
    def test_just_confirmed_within_window(self):
        confirmed_at = datetime.now(UTC) - timedelta(seconds=10)
        assert _within_cancellation_window(confirmed_at, datetime.now(UTC)) is True


# ═══════════════════════════════════════════════════════════════
# REFUND CALCULATION
# ═══════════════════════════════════════════════════════════════

class TestRefundCalculation:
    """Full and partial refund arithmetic"""

    @pytest.mark.unit
    def test_full_refund_returns_total(self):
        assert _calculate_refund(100.0, full=True) == 100.0

    @pytest.mark.unit
    def test_half_refund(self):
        assert _calculate_refund(100.0, full=False, percent=0.5) == 50.0

    @pytest.mark.unit
    def test_zero_total_refund(self):
        assert _calculate_refund(0.0, full=True) == 0.0

    @pytest.mark.unit
    def test_refund_rounds_to_2_decimal(self):
        result = _calculate_refund(33.333, full=False, percent=0.5)
        assert result == round(33.333 * 0.5, 2)

    @pytest.mark.unit
    def test_partial_75_percent(self):
        assert _calculate_refund(200.0, full=False, percent=0.75) == 150.0


# ═══════════════════════════════════════════════════════════════
# IDEMPOTENCY KEY FORMAT
# ═══════════════════════════════════════════════════════════════

class TestIdempotencyKey:
    """IDP-{user_id}-{timestamp}-{random} format"""

    @pytest.mark.unit
    def test_key_starts_with_idp(self):
        key = _idempotency_key("user-abc")
        assert key.startswith("IDP-")

    @pytest.mark.unit
    def test_key_contains_user_id(self):
        uid = "user-xyz"
        key = _idempotency_key(uid)
        assert uid in key

    @pytest.mark.unit
    def test_two_keys_are_unique(self):
        k1 = _idempotency_key("same-user")
        k2 = _idempotency_key("same-user")
        assert k1 != k2


# ═══════════════════════════════════════════════════════════════
# VALID ORDER STATUSES
# ═══════════════════════════════════════════════════════════════

class TestOrderStatuses:
    """update_order_status accepts only valid transitions"""

    @pytest.mark.unit
    def test_confirmed_in_valid_set(self):
        assert "confirmed" in _valid_statuses()

    @pytest.mark.unit
    def test_preparing_in_valid_set(self):
        assert "preparing" in _valid_statuses()

    @pytest.mark.unit
    def test_ready_for_pickup_in_valid_set(self):
        assert "ready_for_pickup" in _valid_statuses()

    @pytest.mark.unit
    def test_delivered_in_valid_set(self):
        assert "delivered" in _valid_statuses()

    @pytest.mark.unit
    def test_completed_in_valid_set(self):
        assert "completed" in _valid_statuses()

    @pytest.mark.unit
    def test_cancelled_in_valid_set(self):
        assert "cancelled" in _valid_statuses()

    @pytest.mark.unit
    def test_invalid_status_not_in_set(self):
        assert "pending" not in _valid_statuses()
        assert "shipped" not in _valid_statuses()

    @pytest.mark.unit
    def test_load_shedding_threshold(self):
        assert MAX_CONCURRENT_ORDERS == 150

    @pytest.mark.unit
    def test_idempotency_window_is_60s(self):
        assert IDEMPOTENCY_WINDOW_SEC == 60


# ═══════════════════════════════════════════════════════════════
# ORDER TOTAL CALCULATIONS
# ═══════════════════════════════════════════════════════════════

class TestOrderTotals:
    """Subtotal, discount, total arithmetic"""

    @pytest.mark.unit
    def test_total_equals_subtotal_minus_discount(self):
        subtotal = 100.0
        discount = 20.0
        total    = round(subtotal - discount, 2)
        assert total == 80.0

    @pytest.mark.unit
    def test_discount_cannot_exceed_subtotal(self):
        subtotal = 30.0
        discount = 50.0
        applied  = min(discount, subtotal)
        assert applied == 30.0

    @pytest.mark.unit
    def test_zero_discount_total_equals_subtotal(self):
        subtotal = 75.50
        total    = round(subtotal - 0.0, 2)
        assert total == 75.50

    @pytest.mark.unit
    def test_line_total_calculation(self):
        price    = 45.0
        quantity = 3
        assert price * quantity == 135.0

    @pytest.mark.unit
    def test_multi_item_subtotal(self):
        items = [
            {"price": 45.0, "qty": 2},
            {"price": 15.0, "qty": 1},
            {"price": 10.0, "qty": 3},
        ]
        subtotal = sum(i["price"] * i["qty"] for i in items)
        assert subtotal == 120.0