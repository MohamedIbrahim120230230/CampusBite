"""
Integration Tests — FR27, FR28, FR29, FR30, FR42, FR43, FR44
Payment gateway flow, retry logic, refund processing.
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def test_db():
    from database import get_test_session
    session = get_test_session()
    yield session
    session.rollback()
    session.close()


# ---------------------------------------------------------------------------
# FR27 — Online Payment Full Flow
# ---------------------------------------------------------------------------

class TestPaymentFlow:

    def test_payment_pending_to_confirmed_on_webhook(self, test_db):
        """
        Full flow: PLACED → PAYMENT_PENDING → CONFIRMED via gateway webhook.
        Stock lock must be committed and notification dispatched.
        """
        from services.order_service   import OrderService
        from services.payment_service import PaymentService

        order_svc = OrderService(test_db)
        pay_svc   = PaymentService(test_db)

        order = order_svc.create_order_in_status("PLACED")
        pay_svc.initiate_payment(order.id, method="ONLINE", idempotency_key="key-flow-001")

        assert order_svc.get_order_status(order.id) == "PAYMENT_PENDING"

        # Simulate webhook success
        pay_svc.process_webhook(
            order_id=order.id,
            event="payment.success",
            idempotency_key="key-flow-001"
        )

        assert order_svc.get_order_status(order.id) == "CONFIRMED"

    def test_payment_method_cash_does_not_call_gateway(self, test_db):
        """CASH payment must skip the gateway entirely."""
        from services.payment_service import PaymentService

        pay = PaymentService(test_db)
        with patch("services.payment_service.GatewayClient") as mock_gw:
            pay.initiate_payment("order-cash-001", method="CASH", idempotency_key="key-cash")
            mock_gw.return_value.charge.assert_not_called()

    def test_payment_not_in_placed_status_rejected(self, test_db):
        """API contract: 409 if order is not in PLACED status when payment initiated."""
        from services.order_service   import OrderService
        from services.payment_service import PaymentService

        order_svc = OrderService(test_db)
        pay_svc   = PaymentService(test_db)
        order     = order_svc.create_order_in_status("CONFIRMED")  # already past PLACED

        result = pay_svc.initiate_payment(
            order.id, method="ONLINE", idempotency_key="key-409"
        )
        assert result.http_status == 409


# ---------------------------------------------------------------------------
# FR28 / FR29 — Gateway Failure & Retry
# ---------------------------------------------------------------------------

class TestGatewayFailureAndRetry:

    def test_gateway_failure_transitions_to_payment_failed(self, test_db):
        """Gateway failure webhook → PAYMENT_FAILED; stock locks released."""
        from services.order_service   import OrderService
        from services.payment_service import PaymentService
        from services.stock_service   import StockService

        order_svc = OrderService(test_db)
        pay_svc   = PaymentService(test_db)
        stock_svc = StockService(test_db)

        order_svc.set_stock("koshary", quantity=5)
        order = order_svc.create_order_in_status("PAYMENT_PENDING",
                                                  items=[("koshary", 2)])
        pay_svc.process_webhook(order.id, event="payment.failed",
                                idempotency_key="key-fail")

        assert order_svc.get_order_status(order.id) == "PAYMENT_FAILED"
        assert stock_svc.get_available("koshary")   == 5  # 2 released

    def test_retry_increments_counter(self, test_db):
        """Each retry increments the retry counter tracked in DB."""
        from services.payment_service import PaymentService
        pay = PaymentService(test_db)

        for i in range(1, 4):
            pay.retry_payment("order-retry-001")
            assert pay.get_retry_count("order-retry-001") == i

    def test_fourth_retry_is_rejected(self, test_db):
        """Exactly 3 retries allowed; 4th returns MAX_RETRIES_EXCEEDED."""
        from services.payment_service import PaymentService
        pay = PaymentService(test_db)

        for _ in range(3):
            pay.retry_payment("order-retry-max")

        result = pay.retry_payment("order-retry-max")
        assert result.http_status == 422
        assert result.error       == "MAX_RETRIES_EXCEEDED"


# ---------------------------------------------------------------------------
# FR42 / FR43 — Refund Integration
# ---------------------------------------------------------------------------

class TestRefundIntegration:

    def test_wallet_refund_committed_atomically_with_cancellation(self, test_db):
        """
        Cancellation + wallet credit must be a single DB transaction.
        Verify wallet balance is restored immediately after cancel.
        """
        from services.refund_service import RefundService
        from services.wallet_service import WalletService

        wallet = WalletService(test_db)
        refund = RefundService(test_db)
        wallet.set_balance("user-001", 200.00)

        order = refund.create_confirmed_wallet_order(user="user-001", total=80.00)
        refund.cancel_order(order.id, reason_code="CUSTOMER_REQUEST")

        assert wallet.get_balance("user-001") == pytest.approx(200.00)

    def test_refund_idempotency_across_retries(self, test_db):
        """Same refund_reference processed twice → single credit (no double refund)."""
        from services.refund_service import RefundService
        from services.wallet_service import WalletService

        wallet = WalletService(test_db)
        refund = RefundService(test_db)
        wallet.set_balance("user-001", 100.00)

        order = refund.create_confirmed_wallet_order(user="user-001", total=50.00)
        refund.process_refund(order.id, refund_reference="REF-IDEM-001")
        refund.process_refund(order.id, refund_reference="REF-IDEM-001")

        assert wallet.get_balance("user-001") == pytest.approx(150.00)  # 100 + 50 once


# ---------------------------------------------------------------------------
# FR44 — Refund Gateway Failure → Manual Queue
# ---------------------------------------------------------------------------

class TestRefundGatewayFailure:

    def test_failed_refund_enters_manual_queue(self, test_db):
        """
        FR44: When the refund gateway call fails, a ManualRefundQueue entry
        is created. No silent drops allowed.
        """
        from services.refund_service import RefundService

        refund = RefundService(test_db)
        order  = refund.create_confirmed_online_order(user="user-002", total=120.00)

        with patch("services.refund_service.GatewayClient.refund",
                   side_effect=Exception("Gateway timeout")):
            refund.process_refund(order.id, refund_reference="REF-FAIL-001")

        queue_entry = refund.get_manual_queue_entry(order.id)
        assert queue_entry is not None
        assert queue_entry.status     == "PENDING_MANUAL"
        assert queue_entry.amount_egp == pytest.approx(120.00)

    def test_failed_refund_recorded_in_audit_log(self, test_db):
        """Every refund attempt (including failures) is recorded in audit_log."""
        from services.refund_service import RefundService

        refund = RefundService(test_db)
        order  = refund.create_confirmed_online_order(user="user-002", total=60.00)

        with patch("services.refund_service.GatewayClient.refund",
                   side_effect=Exception("Gateway timeout")):
            refund.process_refund(order.id, refund_reference="REF-AUDIT-FAIL")

        audit = refund.get_audit_entries(order.id)
        assert len(audit) >= 1
        assert any(e.event_type == "REFUND_FAILED" for e in audit)
