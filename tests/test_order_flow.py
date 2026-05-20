"""
Integration Tests — FR22, FR23, FR30, FR32, FR40
Stock locking concurrency, payment idempotency, wallet atomicity,
auto-cancel on timeout.

These tests use real DB transactions (via a test DB session) and Redis.
Run with: pytest backend/tests/integration/ -v
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch


# ---------------------------------------------------------------------------
# Fixtures — real or near-real DB and Redis connections
# ---------------------------------------------------------------------------

@pytest.fixture
def test_db():
    """
    Provides a test database session with rollback-after-test isolation.
    Replace with your actual test DB session factory.
    """
    from database import get_test_session
    session = get_test_session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def redis_client():
    """Test Redis client (flushes test keys after each test)."""
    import redis
    client = redis.Redis(host="localhost", port=6379, db=15)  # DB 15 = test
    yield client
    client.flushdb()


# ---------------------------------------------------------------------------
# FR22 — Stock Locking: Last Item Can Only Be Bought Once
# ---------------------------------------------------------------------------

class TestStockLocking:

    @pytest.mark.asyncio
    async def test_last_item_can_only_be_bought_once(self, test_db):
        """
        Two concurrent requests for the last unit of stock:
        exactly 1 succeeds (HTTP 200), 1 fails (HTTP 409 OVERSELL_PREVENTED).

        Implementation note: uses SELECT FOR UPDATE NOWAIT at DB level.
        """
        from services.order_service import OrderService

        async def place_order(user_id: str):
            svc = OrderService(test_db)
            return svc.place_order(
                cart_id=f"cart-{user_id}",
                idempotency_key=f"key-{user_id}",
                items=[("koshary", 1)]
            )

        svc = OrderService(test_db)
        svc.set_stock("koshary", quantity=1)

        responses = await asyncio.gather(
            place_order("user1"),
            place_order("user2"),
        )

        success = [r for r in responses if r.status_code == 200]
        failed  = [r for r in responses if r.status_code == 409]

        assert len(success) == 1, "Exactly one order should succeed"
        assert len(failed)  == 1, "Exactly one order should be rejected (OVERSELL_PREVENTED)"

    def test_stock_lock_released_on_payment_failure(self, test_db):
        """FR22: When payment fails, all stock locks for that order are released."""
        from services.order_service  import OrderService
        from services.payment_service import PaymentService
        from services.stock_service   import StockService

        svc   = OrderService(test_db)
        pay   = PaymentService(test_db)
        stock = StockService(test_db)

        svc.set_stock("koshary", quantity=5)
        order = svc.place_order(
            cart_id="cart-lock-test",
            idempotency_key="key-lock-test",
            items=[("koshary", 2)]
        )

        # Simulate payment failure
        pay.simulate_gateway_timeout(order.order_id)

        available = stock.get_available("koshary")
        assert available == 5, (
            "All 2 units must be released — available should return to 5"
        )


# ---------------------------------------------------------------------------
# FR23 / FR30 — Payment Idempotency
# ---------------------------------------------------------------------------

class TestPaymentIdempotency:

    def test_same_idempotency_key_returns_same_transaction(self, test_db):
        """
        FR30: Duplicate payment attempt with same idempotency key returns
        the original transaction — no double charge.
        """
        from services.payment_service import PaymentService
        pay = PaymentService(test_db)

        first  = pay.pay(order_id="order-001", idempotency_key="abc")
        second = pay.pay(order_id="order-001", idempotency_key="abc")

        assert first.transaction_id == second.transaction_id
        # Verify only 1 payment record in DB
        count = pay.count_payment_records(idempotency_key="abc")
        assert count == 1

    def test_different_keys_create_separate_records(self, test_db):
        """Different idempotency keys legitimately create separate payments."""
        from services.payment_service import PaymentService
        pay = PaymentService(test_db)

        first  = pay.pay(order_id="order-002", idempotency_key="key-A")
        second = pay.pay(order_id="order-002", idempotency_key="key-B")

        assert first.transaction_id != second.transaction_id


# ---------------------------------------------------------------------------
# FR32 — Wallet Atomicity
# ---------------------------------------------------------------------------

class TestWalletAtomicity:

    def test_wallet_balance_restored_on_order_failure(self, test_db):
        """
        FR32: If an order fails after wallet deduction, the balance is fully restored.
        Uses a real DB transaction to verify atomicity.
        """
        from services.order_service   import OrderService
        from services.wallet_service  import WalletService

        wallet = WalletService(test_db)
        wallet.set_balance("user1", 100.00)
        balance_before = wallet.get_balance("user1")

        svc = OrderService(test_db)
        svc.force_order_failure_after_wallet_deduction("user1")

        balance_after = wallet.get_balance("user1")
        assert balance_before == balance_after, (
            f"Wallet balance should be restored to {balance_before}; "
            f"got {balance_after}"
        )

    def test_wallet_deduction_and_order_in_single_transaction(self, test_db):
        """
        FR32: Wallet deduction and order status update must occur in one ACID transaction.
        If the order update rolls back, so does the wallet deduction.
        """
        from services.order_service  import OrderService
        from services.wallet_service import WalletService

        wallet = WalletService(test_db)
        wallet.set_balance("user1", 200.00)

        svc = OrderService(test_db)
        with pytest.raises(Exception):
            svc.place_and_deduct_with_forced_rollback(
                user_id="user1",
                order_total=50.00
            )

        # Wallet must not have been debited (transaction rolled back)
        assert wallet.get_balance("user1") == pytest.approx(200.00)


# ---------------------------------------------------------------------------
# FR40 — Auto-Cancel Abandoned Checkout (Integration)
# ---------------------------------------------------------------------------

class TestAutoCancelIntegration:

    def test_cleanup_job_cancels_stale_pending_orders(self, test_db):
        """
        Integration: run_cleanup_job() cancels all orders in PAYMENT_PENDING
        that have been waiting > 600 seconds, and releases their stock locks.
        """
        from services.order_service import OrderService
        from freezegun import freeze_time
        from datetime import datetime, timedelta

        svc   = OrderService(test_db)
        order = svc.create_order_in_status("PAYMENT_PENDING")

        with freeze_time(datetime.utcnow() + timedelta(seconds=600)):
            svc.run_cleanup_job()

        assert svc.get_order_status(order.id) == "CANCELLED"
        assert svc.get_stock_lock_status(order.id) == "RELEASED"

    def test_cleanup_job_does_not_cancel_recent_orders(self, test_db):
        """Cleanup job must not touch orders pending for less than 600 s."""
        from services.order_service import OrderService
        from freezegun import freeze_time
        from datetime import datetime, timedelta

        svc   = OrderService(test_db)
        order = svc.create_order_in_status("PAYMENT_PENDING")

        with freeze_time(datetime.utcnow() + timedelta(seconds=599)):
            svc.run_cleanup_job()

        assert svc.get_order_status(order.id) == "PAYMENT_PENDING"
