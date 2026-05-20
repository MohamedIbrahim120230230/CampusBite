"""
Unit Tests — FR26, FR27, FR28, FR29, FR30, FR31, FR32
Payment processing: method selection, gateway webhook, timeouts, retries,
double-charge prevention, Meal Plan balance, Wallet atomicity.
"""
import pytest
from datetime import timedelta
from unittest.mock import MagicMock, patch
from freezegun import freeze_time

BASE_TIME = "2025-01-01 12:00:00"


@pytest.fixture
def db_session():
    return MagicMock()


@pytest.fixture
def payment_service(db_session):
    from services.payment_service import PaymentService
    return PaymentService(db_session)


# ---------------------------------------------------------------------------
# FR27 — Online Payment Succeeds via Gateway Webhook
# ---------------------------------------------------------------------------

class TestOnlinePaymentWebhook:

    def test_gateway_success_webhook_transitions_to_confirmed(self, payment_service, db_session):
        """
        Gherkin: Gateway success → order transitions PAYMENT_PENDING → CONFIRMED.
        Stock lock converted to committed decrement.
        Notification dispatched within 30 s.
        """
        result = payment_service.process_webhook(
            order_id="order-001",
            event="payment.success",
            idempotency_key="key-webhook-001"
        )
        assert result.order_status          == "CONFIRMED"
        assert result.stock_committed       is True
        assert result.notification_queued   is True

    def test_gateway_redirect_url_only_for_online_method(self, payment_service):
        """API contract: gateway_redirect_url is non-null only for ONLINE method."""
        result_online = payment_service.initiate_payment(
            order_id="order-001", method="ONLINE", idempotency_key="key-online"
        )
        assert result_online.gateway_redirect_url is not None

        result_cash = payment_service.initiate_payment(
            order_id="order-001", method="CASH", idempotency_key="key-cash"
        )
        assert result_cash.gateway_redirect_url is None


# ---------------------------------------------------------------------------
# TDP-M3-03 — FR28-FR30 Gateway Failure, Timeout, Double-Charge Prevention
# ---------------------------------------------------------------------------

class TestPaymentResilience:

    @freeze_time(BASE_TIME)
    def test_gateway_timeout_at_exactly_10_seconds(self, payment_service, db_session):
        """
        PADLOCK P1 — Timeout is exactly 10 seconds:
          At 9 s → PAYMENT_PENDING; at 10 s → PAYMENT_FAILED.
        """
        from datetime import datetime
        base = datetime.fromisoformat(BASE_TIME)

        with freeze_time(base + timedelta(seconds=9)):
            status = payment_service.get_order_status("order-001")
            assert status == "PAYMENT_PENDING"  # P1 — still pending

        with freeze_time(base + timedelta(seconds=10)):
            payment_service.run_timeout_checker()
            status = payment_service.get_order_status("order-001")
            assert status == "PAYMENT_FAILED"   # P1 — failed at exactly 10 s

    def test_payment_failed_releases_stock_lock_atomically(self, payment_service, db_session):
        """
        PADLOCK P2 — Stock release is atomic with status change:
          Cannot have PAYMENT_FAILED + still-locked stock.
        """
        payment_service.simulate_gateway_timeout("order-001")
        stock_status = payment_service.get_stock_lock_status("order-001")
        order_status = payment_service.get_order_status("order-001")

        assert order_status  == "PAYMENT_FAILED"
        assert stock_status  == "RELEASED"  # P2 — released atomically with status change

    def test_retry_allowed_up_to_3_attempts(self, payment_service, db_session):
        """PADLOCK P3 — Max retries is exactly 3: 3rd allowed, 4th rejected."""
        for attempt in range(1, 4):
            result = payment_service.retry_payment("order-001")
            assert result.http_status == 200, f"Attempt {attempt} should be allowed"

        fourth = payment_service.retry_payment("order-001")
        assert fourth.http_status == 422              # P3
        assert fourth.error       == "MAX_RETRIES_EXCEEDED"  # exact error code

    def test_idempotency_key_prevents_double_charge(self, payment_service, db_session):
        """
        PADLOCK P4 — Same idempotency key → exactly 1 PaymentRecord in DB.
        """
        key = "idem-key-payment-001"
        payment_service.simulate_gateway_success("order-001", idempotency_key=key)
        payment_service.simulate_gateway_success("order-001", idempotency_key=key)  # retry

        record_count = (
            db_session.query.return_value
            .filter_by.return_value
            .count.return_value
        )
        # Implementation must only insert 1 PaymentRecord for the same key
        assert db_session.add.call_count == 1, (
            "Only 1 PaymentRecord should be created for the same idempotency key"
        )  # P4


# ---------------------------------------------------------------------------
# FR28 — Gateway Failure Student-Facing Message
# ---------------------------------------------------------------------------

def test_gateway_timeout_message_is_exact(payment_service):
    """Exact message from Gherkin scenario for timeout."""
    payment_service.simulate_gateway_timeout("order-001")
    result = payment_service.get_order_result("order-001")
    assert result.student_message == (
        "Payment timed out. Your cart is available to retry."
    )


# ---------------------------------------------------------------------------
# FR31 — Meal Plan Balance Validation
# ---------------------------------------------------------------------------

class TestMealPlanPayment:

    def test_insufficient_meal_plan_balance_returns_402(self, payment_service):
        """
        Gherkin: Wallet balance 45 EGP, order total 60 EGP → HTTP 402.
        PADLOCK P5 — Response includes current_balance, required, and shortfall.
        """
        result = payment_service.initiate_payment(
            order_id="order-001",
            method="MEAL_PLAN",
            idempotency_key="key-meal",
            user_balance=45.00,
            order_total=60.00
        )
        assert result.http_status       == 402
        assert result.current_balance   == 45.00  # P5
        assert result.required          == 60.00  # P5
        assert result.shortfall         == 15.00  # P5
        # No deduction on insufficient balance
        assert result.deducted          is False

    def test_sufficient_meal_plan_balance_accepted(self, payment_service):
        """Meal Plan with sufficient balance proceeds normally."""
        result = payment_service.initiate_payment(
            order_id="order-002",
            method="MEAL_PLAN",
            idempotency_key="key-meal-ok",
            user_balance=100.00,
            order_total=60.00
        )
        assert result.http_status == 200
        assert result.status      == "PAYMENT_PENDING"


# ---------------------------------------------------------------------------
# FR32 — Wallet Atomic Deduction
# ---------------------------------------------------------------------------

class TestWalletAtomicity:

    def test_wallet_deduction_insufficient_balance_rejected(self, payment_service):
        """
        Gherkin: Wallet 45 EGP, order 60 EGP → HTTP 402.
        Error message must include current balance and required amount.
        """
        result = payment_service.initiate_payment(
            order_id="order-003",
            method="WALLET",
            idempotency_key="key-wallet",
            user_balance=45.00,
            order_total=60.00
        )
        assert result.http_status == 402
        assert "45" in result.message
        assert "60" in result.message

    def test_wallet_deduction_does_not_occur_on_insufficient_balance(self, payment_service, db_session):
        """No deduction made when balance is insufficient (FR32)."""
        payment_service.initiate_payment(
            order_id="order-003",
            method="WALLET",
            idempotency_key="key-wallet-no-deduct",
            user_balance=45.00,
            order_total=60.00
        )
        # Verify no wallet update was committed
        wallet_updates = [
            call for call in db_session.add.call_args_list
            if "wallet" in str(call).lower()
        ]
        assert len(wallet_updates) == 0

    def test_circuit_breaker_open_returns_503(self, payment_service):
        """
        API contract: 503 returned when payment gateway circuit breaker is open.
        """
        result = payment_service.initiate_payment(
            order_id="order-circuit",
            method="ONLINE",
            idempotency_key="key-circuit",
            gateway_available=False   # simulate open circuit breaker
        )
        assert result.http_status == 503
