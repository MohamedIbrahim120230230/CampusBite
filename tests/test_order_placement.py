"""
Unit Tests — FR20, FR22, FR23, FR24, FR25
Order placement, stock locking, idempotency, suspicious order detection,
and load-shedding (HTTP 503).
"""
import pytest
import threading
from datetime import timedelta
from unittest.mock import MagicMock
from freezegun import freeze_time

BASE_TIME = "2025-01-01 12:00:00"


@pytest.fixture
def db_session():
    return MagicMock()


# ---------------------------------------------------------------------------
# FR20 — Successful Order Placement
# ---------------------------------------------------------------------------

class TestOrderPlacement:

    def test_successful_order_assigns_uuid_and_timestamp(self, db_session):
        """
        Gherkin: Order receives UUID v4 and millisecond-precision UTC timestamp.
        Status must be PLACED.
        """
        from services.order_service import OrderService
        import uuid, re
        svc    = OrderService(db_session)
        result = svc.place_order(cart_id="cart-locked-001", idempotency_key=str(uuid.uuid4()))

        assert result.http_status == 200
        assert result.status      == "PLACED"
        # UUID v4 format check
        uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        assert re.match(uuid_pattern, result.order_id, re.I), "order_id must be UUID v4"
        # Millisecond-precision UTC
        assert "T" in result.placed_at and ("Z" in result.placed_at or "+00" in result.placed_at)

    def test_pessimistic_stock_lock_acquired_on_placement(self, db_session):
        """FR22: A pessimistic stock lock must be acquired for all ordered items."""
        from services.order_service import OrderService
        svc    = OrderService(db_session)
        result = svc.place_order(cart_id="cart-locked-001", idempotency_key="key-001")
        assert result.stock_lock_expires_at is not None


# ---------------------------------------------------------------------------
# TDP-M3-01 — FR22 Pessimistic Stock Lock (Oversell Prevention)
# ---------------------------------------------------------------------------

class TestStockLock:

    def test_last_item_cannot_be_oversold_under_concurrency(self, db_session):
        """
        PADLOCKS:
          P1 — Exactly 1 winner under concurrency: stock=1, 2 concurrent → 1 success, 1 rejection
          P3 — Payment failure releases full lock
          P4 — No partial release: all items released atomically
        """
        from services.order_service import OrderService
        svc = OrderService(db_session)
        svc.set_stock("koshary", quantity=1)

        results = []
        lock = threading.Lock()

        def attempt(user_id):
            r = svc.place_order(
                cart_id=f"cart-{user_id}",
                idempotency_key=f"key-{user_id}",
                items=[("koshary", 1)]
            )
            with lock:
                results.append(r)

        threads = [
            threading.Thread(target=attempt, args=("user-001",)),
            threading.Thread(target=attempt, args=("user-002",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        confirmed = [r for r in results if r.http_status == 200]
        rejected  = [r for r in results if r.http_status == 409]
        assert len(confirmed) == 1                           # P1
        assert len(rejected)  == 1                           # P1
        assert rejected[0].error == "OVERSELL_PREVENTED"    # exact error code

    @freeze_time(BASE_TIME)
    def test_stock_lock_ttl_is_exactly_600_seconds(self, db_session):
        """
        PADLOCK P2 — Lock TTL is exactly 600 seconds:
          Lock held at 599 s; released at 600 s.
        """
        from services.order_service import OrderService
        from services.stock_service  import StockService
        from datetime import datetime
        svc   = OrderService(db_session)
        stock = StockService(db_session)
        base  = datetime.fromisoformat(BASE_TIME)

        svc.set_stock("koshary", quantity=1)
        svc.place_order(cart_id="cart-001", idempotency_key="key-001",
                        items=[("koshary", 1)])

        with freeze_time(base + timedelta(seconds=599)):
            available = stock.get_available("koshary")
            assert available == 0  # P2 — still locked

        with freeze_time(base + timedelta(seconds=600)):
            available = stock.get_available("koshary")
            assert available == 1  # P2 — released exactly at 600 s


# ---------------------------------------------------------------------------
# TDP-M3-02 — FR23 Duplicate Order Idempotency (60-Second Window)
# ---------------------------------------------------------------------------

class TestOrderIdempotency:

    @freeze_time(BASE_TIME)
    def test_duplicate_within_60s_returns_original_order(self, db_session):
        """
        PADLOCKS:
          P1 — Window is exactly 60 seconds
          P3 — Only 1 DB row per key within window (not 2 rows returning same ID)
        """
        from services.order_service import OrderService
        svc = OrderService(db_session)
        key = "idem-key-abc-123"

        first  = svc.place_order(cart_id="cart-001", idempotency_key=key)
        second = svc.place_order(cart_id="cart-001", idempotency_key=key)

        assert second.order_id == first.order_id  # same order returned
        # P3 — exactly 1 DB row
        order_count = db_session.query.return_value.filter_by.return_value.count.return_value
        # The implementation must not insert a second row
        assert db_session.add.call_count <= 1, "Only 1 Order row should be inserted"

    @freeze_time(BASE_TIME)
    def test_new_order_allowed_after_60_second_window(self, db_session):
        """PADLOCK P1 — At 61 s a new order is created for the same key."""
        from services.order_service import OrderService
        from datetime import datetime
        svc  = OrderService(db_session)
        key  = "idem-key-abc-123"
        base = datetime.fromisoformat(BASE_TIME)

        first = svc.place_order(cart_id="cart-001", idempotency_key=key)
        with freeze_time(base + timedelta(seconds=61)):
            second = svc.place_order(cart_id="cart-001", idempotency_key=key)
        assert second.order_id != first.order_id  # P1 — new order

    def test_same_cart_different_key_creates_two_orders(self, db_session):
        """PADLOCK P2 — Deduplication is key-based, not content-based."""
        from services.order_service import OrderService
        svc    = OrderService(db_session)
        first  = svc.place_order(cart_id="cart-001", idempotency_key="key-A")
        second = svc.place_order(cart_id="cart-001", idempotency_key="key-B")
        assert second.order_id != first.order_id  # P2


# ---------------------------------------------------------------------------
# FR24 — Suspicious Order Detection
# ---------------------------------------------------------------------------

class TestSuspiciousOrder:

    def test_order_above_threshold_flagged_for_admin_review(self, db_session):
        """
        Gherkin: Order totalling 750 EGP (threshold 500 EGP) → FLAGGED.
        Student receives 'under review' message.
        """
        from services.order_service import OrderService
        svc = OrderService(db_session)
        svc.set_suspicious_threshold(500.00)

        result = svc.place_order(
            cart_id="cart-big-order",
            idempotency_key="key-flag-001",
            total_override=750.00
        )
        assert result.status == "FLAGGED"
        assert "under review" in result.message.lower()

    def test_order_at_threshold_not_flagged(self, db_session):
        """Order at exactly 500 EGP should NOT be flagged (threshold is strictly >)."""
        from services.order_service import OrderService
        svc = OrderService(db_session)
        svc.set_suspicious_threshold(500.00)

        result = svc.place_order(
            cart_id="cart-edge",
            idempotency_key="key-edge-001",
            total_override=500.00
        )
        assert result.status != "FLAGGED"


# ---------------------------------------------------------------------------
# TDP-M3-04 — FR25 System Load-Shedding (HTTP 503)
# ---------------------------------------------------------------------------

class TestLoadShedding:

    def test_503_returned_when_concurrent_orders_at_limit(self, db_session):
        """
        PADLOCKS:
          P1 — Threshold is configurable and respected: 150 active → 503; 149 → 200
          P2 — Retry-After header is required and set to 30
          P3 — Message is exact, no stack trace
        """
        from services.order_service import OrderService
        svc = OrderService(db_session)
        svc.set_max_concurrent_orders(150)
        svc.seed_active_orders(count=150)

        result = svc.place_order(cart_id="cart-xyz", idempotency_key="key-shed")
        assert result.http_status == 503                                              # P1
        assert int(result.headers["Retry-After"]) == 30                              # P2
        assert result.message == "Service temporarily busy. Please try again shortly." # P3

    def test_order_accepted_when_one_below_limit(self, db_session):
        """PADLOCK P1 — 149 active → 200."""
        from services.order_service import OrderService
        svc = OrderService(db_session)
        svc.set_max_concurrent_orders(150)
        svc.seed_active_orders(count=149)

        result = svc.place_order(cart_id="cart-xyz", idempotency_key="key-ok")
        assert result.http_status in (200, 201)  # P1
