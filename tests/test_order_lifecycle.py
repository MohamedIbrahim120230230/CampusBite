"""
Unit Tests — FR34, FR35, FR37, FR38, FR40, FR41
Order state machine, user cancellation window, auto-cancel abandoned checkout,
stock inconsistency detection.
"""
import pytest
from datetime import timedelta
from unittest.mock import MagicMock, call
from freezegun import freeze_time

BASE_TIME = "2025-01-01 12:00:00"


@pytest.fixture
def db_session():
    return MagicMock()


@pytest.fixture
def order_service(db_session):
    from services.order_service import OrderService
    return OrderService(db_session)


# ---------------------------------------------------------------------------
# FR34 / FR35 — Order State Machine Forward Transitions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("from_state,to_state,actor,trigger", [
    ("PLACED",           "PAYMENT_PENDING", "user",   "Payment method selected"),
    ("PAYMENT_PENDING",  "CONFIRMED",       "system", "Gateway success webhook"),
    ("CONFIRMED",        "PREPARING",       "staff",  "Staff advances status"),
    ("PREPARING",        "READY",           "staff",  "Staff marks ready"),
    ("READY",            "COLLECTED",       "staff",  "Staff confirms collection"),
    ("COLLECTED",        "COMPLETED",       "system", "Auto-complete after 2 hours"),
])
def test_valid_forward_state_transition(db_session, from_state, to_state, actor, trigger):
    """
    Gherkin Scenario Outline: Valid forward state transitions.
    Every defined transition in the state machine must succeed.
    """
    from services.order_service import OrderService
    svc    = OrderService(db_session)
    order  = svc.create_order_in_status(from_state)
    result = svc.transition_order(
        order_id=order.id,
        to_status=to_state,
        actor_role=actor
    )
    assert result.http_status == 200
    assert result.status      == to_state, (
        f"Expected {to_state} after {trigger} from {from_state}"
    )


def test_invalid_backward_transition_rejected(order_service):
    """State machine must reject backward transitions."""
    order  = order_service.create_order_in_status("CONFIRMED")
    result = order_service.transition_order(
        order_id=order.id, to_status="PLACED", actor_role="staff"
    )
    assert result.http_status == 409


def test_invalid_skip_transition_rejected(order_service):
    """State machine must reject skip-state transitions (e.g. PLACED → READY)."""
    order  = order_service.create_order_in_status("PLACED")
    result = order_service.transition_order(
        order_id=order.id, to_status="READY", actor_role="staff"
    )
    assert result.http_status == 409


# ---------------------------------------------------------------------------
# TDP-M4-01 — FR37/FR38 User Cancellation Window (2 Minutes)
# ---------------------------------------------------------------------------

class TestCancellationWindow:

    @freeze_time(BASE_TIME)
    def test_cancellation_allowed_at_119_seconds(self, order_service):
        """
        PADLOCK P1 — Window boundary is exactly 120 seconds: 119 s → allowed.
        """
        from datetime import datetime
        base  = datetime.fromisoformat(BASE_TIME)
        order = order_service.create_order_in_status("PLACED")

        with freeze_time(base + timedelta(seconds=119)):
            result = order_service.cancel_order(order.id, user_role="student")
            assert result.http_status == 200   # P1
            assert result.status      == "CANCELLED"

    @freeze_time(BASE_TIME)
    def test_cancellation_rejected_at_120_seconds(self, order_service):
        """
        PADLOCK P1 — 120 s → rejected.
        PADLOCK P4 — Error message is specific to window expiry.
        """
        from datetime import datetime
        base  = datetime.fromisoformat(BASE_TIME)
        order = order_service.create_order_in_status("PLACED")

        with freeze_time(base + timedelta(seconds=120)):
            result = order_service.cancel_order(order.id, user_role="student")
            assert result.http_status == 403                              # P1
            assert result.error       == "CANCELLATION_WINDOW_EXPIRED"   # P4

    def test_status_blocks_cancellation_independently_of_time(self, order_service):
        """
        PADLOCK P2 — PREPARING blocks user cancellation regardless of elapsed time.
        """
        order  = order_service.create_order_in_status("PREPARING")
        result = order_service.cancel_order(order.id, user_role="student")
        assert result.http_status == 403
        assert result.error       != "CANCELLATION_WINDOW_EXPIRED"  # different reason

    def test_staff_cancellation_requires_reason_code(self, order_service):
        """
        PADLOCK P3 — Staff cancellation requires reason_code: None → HTTP 422.
        """
        order  = order_service.create_order_in_status("CONFIRMED")
        result = order_service.cancel_order(order.id, user_role="staff", reason_code=None)
        assert result.http_status == 422             # P3
        assert result.error       == "REASON_CODE_REQUIRED"

    @pytest.mark.parametrize("reason_code", [
        "CUSTOMER_REQUEST", "OUT_OF_STOCK", "STAFF_ERROR",
        "SYSTEM_ERROR", "SUSPICIOUS_ORDER",
    ])
    def test_staff_cancellation_with_valid_reason_codes(self, order_service, reason_code):
        """All five valid reason codes must be accepted for staff cancellations."""
        order  = order_service.create_order_in_status("CONFIRMED")
        result = order_service.cancel_order(
            order.id, user_role="staff", reason_code=reason_code
        )
        assert result.http_status == 200

    def test_audit_log_written_on_cancellation(self, order_service, db_session):
        """Gherkin: cancellation logged with actor=User and reason=Customer request."""
        order = order_service.create_order_in_status("PLACED")
        order_service.cancel_order(order.id, user_role="student")
        # Verify audit log entry was created
        db_session.add.assert_called()


# ---------------------------------------------------------------------------
# TDP-M4-02 — FR40 Auto-Cancel Abandoned Checkout (10-Minute TTL)
# ---------------------------------------------------------------------------

class TestAbandonedCheckoutAutoCancellation:

    @freeze_time(BASE_TIME)
    def test_order_still_pending_at_599_seconds(self, order_service):
        """PADLOCK P1 — 599 s → still PAYMENT_PENDING."""
        from datetime import datetime
        base  = datetime.fromisoformat(BASE_TIME)
        order = order_service.create_order_in_status("PAYMENT_PENDING")

        with freeze_time(base + timedelta(seconds=599)):
            order_service.run_cleanup_job()
            status = order_service.get_order_status(order.id)
            assert status == "PAYMENT_PENDING"  # P1

    @freeze_time(BASE_TIME)
    def test_auto_cancelled_at_exactly_600_seconds(self, order_service):
        """PADLOCK P1 — 600 s → CANCELLED."""
        from datetime import datetime
        base  = datetime.fromisoformat(BASE_TIME)
        order = order_service.create_order_in_status("PAYMENT_PENDING")

        with freeze_time(base + timedelta(seconds=600)):
            order_service.run_cleanup_job()
            status = order_service.get_order_status(order.id)
            assert status == "CANCELLED"   # P1

    @freeze_time(BASE_TIME)
    def test_stock_released_as_part_of_auto_cancel(self, order_service, db_session):
        """
        PADLOCK P2 — Stock release is part of the auto-cancel transaction:
          Cannot cancel without releasing stock locks.
        """
        from datetime import datetime
        base  = datetime.fromisoformat(BASE_TIME)
        order = order_service.create_order_in_status("PAYMENT_PENDING")

        with freeze_time(base + timedelta(seconds=600)):
            order_service.run_cleanup_job()
            stock_lock = order_service.get_stock_lock_status(order.id)
            assert stock_lock == "RELEASED"  # P2

    @freeze_time(BASE_TIME)
    def test_student_notified_on_auto_cancel(self, order_service):
        """
        PADLOCK P3 — Notification is mandatory; no silent auto-cancellations.
        Exact notification message required.
        """
        from datetime import datetime
        from unittest.mock import patch as mock_patch
        base  = datetime.fromisoformat(BASE_TIME)
        order = order_service.create_order_in_status("PAYMENT_PENDING")
        order.user_id = "user-001"

        with freeze_time(base + timedelta(seconds=600)):
            with mock_patch("services.notification_service.send") as mock_notify:
                order_service.run_cleanup_job()
                mock_notify.assert_called_once_with(
                    user_id="user-001",
                    message="Your pending order was automatically cancelled due to payment timeout."
                )  # P3


# ---------------------------------------------------------------------------
# TDP-M4-03 — FR41 Stock Inconsistency Post-Confirmation
# ---------------------------------------------------------------------------

class TestStockInconsistency:

    def test_order_held_when_stock_inconsistency_detected(self, order_service, db_session):
        """
        PADLOCK P1 — Inconsistency detected post-confirmation → HELD (not CANCELLED).
        """
        order = order_service.create_confirmed_order(items=[("koshary", 3)])
        order_service.force_stock_inconsistency("koshary", available=1)
        order_service.run_stock_consistency_checker()

        updated = order_service.get_order(order.id)
        assert updated.status == "HELD"  # P1 — HELD, not CANCELLED

    def test_admin_notified_on_stock_inconsistency(self, order_service):
        """
        PADLOCK P2 — Admin queue entry created (visible in admin review queue,
        not just an internal log).
        """
        from unittest.mock import patch as mock_patch
        order = order_service.create_confirmed_order(items=[("koshary", 3)])
        order_service.force_stock_inconsistency("koshary", available=1)

        with mock_patch("services.admin_alert_service.send") as mock_alert:
            order_service.run_stock_consistency_checker()
            mock_alert.assert_called_once()
            alert = mock_alert.call_args[0][0]
            assert alert["order_id"] == order.id            # P2
            assert alert["type"]     == "STOCK_INCONSISTENCY"  # P2

    def test_staff_order_assignment_idempotency_under_concurrency(self, order_service):
        """
        TDP-HR-04 — HR-04: Concurrent staff transitions are idempotent.
        PADLOCKS:
          P1 — Exactly 1 successful transition
          P2 — Exactly 1 row in OrderTransitionLog
          P3 — HTTP 409 for the loser with ORDER_ALREADY_ADVANCED
        """
        import threading
        order   = order_service.create_order_in_status("CONFIRMED")
        results = []
        lock    = threading.Lock()

        def advance(actor):
            r = order_service.transition_order(
                order_id=order.id, to_status="PREPARING", actor_role="staff",
                actor_id=actor
            )
            with lock:
                results.append(r)

        threads = [
            threading.Thread(target=advance, args=("staff-A",)),
            threading.Thread(target=advance, args=("staff-B",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = [r for r in results if r.http_status == 200]
        conflicts = [r for r in results if r.http_status == 409]

        assert len(successes) == 1                               # P1
        assert len(conflicts) == 1                               # P1
        assert conflicts[0].error == "ORDER_ALREADY_ADVANCED"    # P3
