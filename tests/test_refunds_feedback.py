"""
Unit Tests — FR42, FR43, FR44, FR45, FR47, FR48, FR49
Refunds, partial refunds, feedback/ratings.
Also covers HR-02 (Meal Plan activation lag) and HR-07 (cross-device cart).
"""
import pytest
from unittest.mock import MagicMock, patch as mock_patch


@pytest.fixture
def db_session():
    return MagicMock()


# ---------------------------------------------------------------------------
# TDP-M5-01 — FR42/FR43 Refund Initiation & Wallet Idempotency
# ---------------------------------------------------------------------------

class TestRefunds:

    def test_wallet_refund_is_atomic_and_immediate(self, db_session):
        """
        PADLOCK P1 — Wallet refund in same transaction as cancellation:
          No window where order is CANCELLED but wallet not credited.
        """
        from services.refund_service import RefundService
        svc = RefundService(db_session)
        svc.set_wallet_balance("user-001", balance=100.00)
        order = svc.create_confirmed_wallet_order(user="user-001", total=60.00)

        svc.cancel_order(order.id, reason_code="CUSTOMER_REQUEST")

        assert svc.get_wallet_balance("user-001") == pytest.approx(100.00)  # P1

    def test_wallet_refund_is_idempotent(self, db_session):
        """
        PADLOCK P2 — Refund idempotency prevents double-credit:
          Same refund_reference → credited exactly once (wallet 100 + 60 = 160, not 220).
        """
        from services.refund_service import RefundService
        svc = RefundService(db_session)
        svc.set_wallet_balance("user-001", balance=100.00)
        order = svc.create_confirmed_wallet_order(user="user-001", total=60.00)

        svc.process_refund(order.id, refund_reference="REF-001")
        svc.process_refund(order.id, refund_reference="REF-001")  # duplicate

        balance = svc.get_wallet_balance("user-001")
        assert balance == pytest.approx(160.00)  # P2 — credited exactly once

    def test_failed_gateway_refund_added_to_manual_queue(self, db_session):
        """
        PADLOCK P3 — Gateway failure creates queue entry — no silent drop:
          ManualRefundQueue row must exist with status=PENDING_MANUAL.
        """
        from services.refund_service import RefundService
        svc = RefundService(db_session)
        order = svc.create_confirmed_wallet_order(user="user-001", total=120.00)

        svc.simulate_gateway_refund_failure(order.id)

        # Verify manual queue entry was created
        db_session.add.assert_called()
        # The last added object should be a ManualRefundQueue entry
        added = db_session.add.call_args[0][0]
        assert hasattr(added, "status")
        assert added.status      == "PENDING_MANUAL"  # P3
        assert added.amount_egp  == pytest.approx(120.00)

    def test_audit_log_records_every_refund_attempt(self, db_session):
        """Audit log must record success, failure, and duplicate-skip events."""
        from services.refund_service import RefundService
        svc = RefundService(db_session)
        svc.set_wallet_balance("user-001", balance=100.00)
        order = svc.create_confirmed_wallet_order(user="user-001", total=60.00)

        svc.process_refund(order.id, refund_reference="REF-AUDIT-001")
        svc.process_refund(order.id, refund_reference="REF-AUDIT-001")  # duplicate

        audit_calls = [
            call for call in db_session.add.call_args_list
            if "audit" in str(call).lower()
        ]
        assert len(audit_calls) >= 2  # success + duplicate-skip


# ---------------------------------------------------------------------------
# TDP-M5-02 — FR45 Partial Refund on Partial Fulfilment
# ---------------------------------------------------------------------------

class TestPartialRefund:

    def test_partial_refund_covers_unfulfilled_items_only(self, db_session):
        """
        Order: koshary 35 EGP (FULFILLED) + grilled_chicken 65 EGP (NOT_FULFILLED)
               + juice 20 EGP (FULFILLED)
        Refund must equal 65 EGP — only the unfulfilled item.

        PADLOCK P1 — Refund = sum of unfulfilled items only.
        """
        from services.refund_service import RefundService
        svc    = RefundService(db_session)
        order  = svc.create_order_with_items([
            {"name": "koshary",         "price": 35.00, "fulfilled": True},
            {"name": "grilled_chicken", "price": 65.00, "fulfilled": False},
            {"name": "juice",           "price": 20.00, "fulfilled": True},
        ])
        result = svc.process_partial_refund(order.id, unfulfilled_items=["grilled_chicken"])

        assert result.refund_amount_egp == pytest.approx(65.00)  # P1 — only unfulfilled
        assert result.refund_amount_egp != pytest.approx(120.00) # not full total
        assert result.refund_amount_egp != pytest.approx(55.00)  # not fulfilled items sum

    def test_partial_refund_requires_staff_or_admin_role(self, db_session):
        """PADLOCK P2 — Only staff/admin can trigger partial refund."""
        from services.refund_service import RefundService
        svc    = RefundService(db_session)
        order  = svc.create_order_with_items([
            {"name": "grilled_chicken", "price": 65.00, "fulfilled": False},
        ])
        result = svc.process_partial_refund(
            order.id, unfulfilled_items=["grilled_chicken"], actor_role="student"
        )
        assert result.http_status == 403        # P2
        assert result.error       == "INSUFFICIENT_ROLE"

    def test_partial_refund_is_append_only_in_audit_log(self, db_session):
        """PADLOCK P3 — Refund recorded in audit_log; append-only (no edits)."""
        from services.refund_service import RefundService
        svc   = RefundService(db_session)
        order = svc.create_order_with_items([
            {"name": "grilled_chicken", "price": 65.00, "fulfilled": False},
        ])
        svc.process_partial_refund(
            order.id, unfulfilled_items=["grilled_chicken"], actor_role="staff"
        )
        # Confirm an audit entry was added (not updated)
        db_session.add.assert_called()


# ---------------------------------------------------------------------------
# TDP-M5-03 — FR47 Feedback Submission (Post-COMPLETED Only)
# ---------------------------------------------------------------------------

class TestFeedback:

    def test_rating_accepted_for_completed_order(self, db_session):
        """PADLOCK P1 — Rating allowed for COMPLETED status only."""
        from services.feedback_service import FeedbackService
        svc    = FeedbackService(db_session)
        order  = svc.create_order_in_status("COMPLETED")
        result = svc.submit_rating(order.id, stars=4, comment="Good portion size!")
        assert result.http_status == 200  # P1

    @pytest.mark.parametrize("status", [
        "PLACED", "CONFIRMED", "PREPARING", "READY", "CANCELLED"
    ])
    def test_rating_blocked_for_non_completed_statuses(self, db_session, status):
        """PADLOCK P1 — All 5 non-COMPLETED statuses → HTTP 403."""
        from services.feedback_service import FeedbackService
        svc    = FeedbackService(db_session)
        order  = svc.create_order_in_status(status)
        result = svc.submit_rating(order.id, stars=5)
        assert result.http_status == 403  # P1

    def test_rating_cannot_be_edited_after_submission(self, db_session):
        """
        PADLOCK P2 — No editing after submission:
          Second submit → 409, original rating unchanged.
        """
        from services.feedback_service import FeedbackService
        svc   = FeedbackService(db_session)
        order = svc.create_order_in_status("COMPLETED")

        svc.submit_rating(order.id, stars=4)
        second = svc.submit_rating(order.id, stars=2)

        assert second.http_status == 409                       # P2
        assert second.error       == "RATING_ALREADY_SUBMITTED"
        # Original rating must remain 4
        stored = svc.get_rating(order.id)
        assert stored.stars == 4                               # P2

    @pytest.mark.parametrize("stars,expected_status", [
        (0, 422), (6, 422),   # P3 — out of range
        (1, 200), (5, 200),   # P3 — boundary values allowed
    ])
    def test_star_rating_range_validation(self, db_session, stars, expected_status):
        """PADLOCK P3 — Stars range: 1-5 inclusive. 0 and 6 → 422."""
        from services.feedback_service import FeedbackService
        svc   = FeedbackService(db_session)
        order = svc.create_order_in_status("COMPLETED")

        result = svc.submit_rating(order.id, stars=stars)
        assert result.http_status == expected_status  # P3


# ---------------------------------------------------------------------------
# TDP-HR-01 — HR-02 Meal Plan Activation Lag
# ---------------------------------------------------------------------------

class TestMealPlanActivationLag:

    def test_pending_activation_distinct_from_insufficient_balance(self, db_session):
        """
        PADLOCK P1 — Two distinct error codes required:
          MEAL_PLAN_NOT_YET_ACTIVATED ≠ INSUFFICIENT_MEAL_PLAN_BALANCE
        PADLOCK P2 — PENDING_ACTIVATION checked before balance.
        """
        from services.payment_service import PaymentService
        svc = PaymentService(db_session)

        # PENDING_ACTIVATION — not yet set up
        svc.set_meal_plan_status("user-new", status="PENDING_ACTIVATION")
        result_pending = svc.pay_with_meal_plan(order_total=50.00, user="user-new")
        assert result_pending.error   == "MEAL_PLAN_NOT_YET_ACTIVATED"   # P1
        assert "student services" in result_pending.message.lower()

        # ACTIVE but zero balance — different error
        svc.set_meal_plan_status("user-new", status="ACTIVE", balance=0.00)
        result_zero = svc.pay_with_meal_plan(order_total=50.00, user="user-new")
        assert result_zero.error   == "INSUFFICIENT_MEAL_PLAN_BALANCE"   # P1
        assert result_zero.error   != "MEAL_PLAN_NOT_YET_ACTIVATED"      # P1 — different


# ---------------------------------------------------------------------------
# TDP-HR-07 — HR-07 Cross-Device Cart Invalidation
# ---------------------------------------------------------------------------

class TestCrossDeviceCartInvalidation:

    def test_stale_cart_invalidated_on_second_device(self, db_session):
        """
        PADLOCK P1 — Cart locked by session A blocks session B: HTTP 409.
        PADLOCK P2 — Error code is CART_INVALIDATED (not CART_LOCKED).
        """
        from services.cart_service import CartService
        svc  = CartService(db_session)
        cart = svc.create_cart(user_id="user-001")

        # Device A locks and proceeds to checkout
        svc.lock_cart_for_checkout(cart.id, session_id="session-device-A")

        # Device B tries the same cart
        result = svc.lock_cart_for_checkout(cart.id, session_id="session-device-B")

        assert result.http_status == 409                    # P1
        assert result.error       == "CART_INVALIDATED"    # P2
        assert result.message     == (
            "Your cart was modified on another device. "
            "Please refresh to see the latest state."
        )
