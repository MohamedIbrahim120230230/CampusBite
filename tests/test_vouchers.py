"""
Unit Tests — FR13, FR14, FR15, FR16
Voucher application, validation, floor at zero, concurrency guard.
"""
import pytest
import threading
from unittest.mock import MagicMock


@pytest.fixture
def db_session():
    return MagicMock()


def build_cart(total_egp: float):
    cart = MagicMock()
    cart.total_egp = total_egp
    return cart


def build_voucher(flat_discount_egp=None, percent_discount=None,
                  min_order_egp=0, used=False, expired=False, revoked=False):
    v = MagicMock()
    v.flat_discount_egp   = flat_discount_egp
    v.percent_discount    = percent_discount
    v.min_order_egp       = min_order_egp
    v.used                = used
    v.expired             = expired
    v.revoked             = revoked
    return v


# ---------------------------------------------------------------------------
# TDP-M2-01 — FR13 Valid Voucher Applied
# ---------------------------------------------------------------------------

class TestValidVoucherApplication:

    def test_percentage_voucher_reduces_cart_total(self, db_session):
        """
        Gherkin: SAVE20 (20%) on 120 EGP cart → 96 EGP.
        """
        from services.voucher_service import apply_voucher
        cart    = build_cart(total_egp=120.00)
        voucher = build_voucher(percent_discount=20)
        result  = apply_voucher(cart, voucher, db=db_session)
        assert result.final_total_egp == pytest.approx(96.00)

    def test_voucher_marked_as_used_atomically(self, db_session):
        """Voucher consumed atomically — single DB write, not two separate ops."""
        from services.voucher_service import apply_voucher
        cart    = build_cart(total_egp=120.00)
        voucher = build_voucher(percent_discount=20)
        apply_voucher(cart, voucher, db=db_session)
        db_session.commit.assert_called_once()  # atomic: one commit


# ---------------------------------------------------------------------------
# TDP-M2-01 — FR14-FR16 Invalid Voucher Rejection (Scenario Outline)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code,cart_total,error_message", [
    ("USED01",  80,  "Voucher has already been used by your account."),
    ("EXPD01",  80,  "Voucher has expired."),
    ("MIN100",  50,  "Minimum order of 100 EGP required for this voucher."),
    ("RVKD01",  80,  "Voucher is no longer valid."),
])
def test_invalid_voucher_rejected_with_specific_message(db_session, code, cart_total, error_message):
    """
    PADLOCK P5 — All error messages are exact; no generic fallback allowed.
    """
    from services.voucher_service import apply_voucher, VoucherError

    voucher = MagicMock()
    voucher.code = code
    # Configure the mock to raise VoucherError with exact message
    with pytest.raises(VoucherError) as exc_info:
        apply_voucher(build_cart(cart_total), voucher, db=db_session)

    assert exc_info.value.message == error_message  # P5


# ---------------------------------------------------------------------------
# TDP-M2-01 — Voucher Floors Cart at Zero (Never Negative)
# ---------------------------------------------------------------------------

class TestVoucherFloorAtZero:

    def test_over_discount_floors_total_to_zero(self, db_session):
        """
        Gherkin: 100 EGP flat voucher on 30 EGP cart → 0 EGP (not negative).

        PADLOCKS:
          P1 — Final total floor is zero: final_total_egp >= 0 always
          P2 — Applied discount ≤ cart total: discount_egp capped at cart_total
        """
        from services.voucher_service import apply_voucher
        cart    = build_cart(total_egp=30.00)
        voucher = build_voucher(flat_discount_egp=100.00)
        result  = apply_voucher(cart, voucher, db=db_session)

        assert result.final_total_egp == pytest.approx(0.00)  # P1 — exact zero
        assert result.final_total_egp >= 0.00                 # P1 — never negative
        assert result.discount_egp    == pytest.approx(30.00) # P2 — capped at cart total
        assert result.excess_egp      is None                  # no carryover

    def test_negative_cart_total_never_stored(self, db_session):
        """No negative amount is ever stored or transmitted."""
        from services.voucher_service import apply_voucher
        cart    = build_cart(total_egp=10.00)
        voucher = build_voucher(flat_discount_egp=500.00)
        result  = apply_voucher(cart, voucher, db=db_session)
        assert result.final_total_egp >= 0.00


# ---------------------------------------------------------------------------
# TDP-M2-01 — Concurrent Single-Use Voucher (First Wins)
# ---------------------------------------------------------------------------

class TestConcurrentVoucher:

    def test_concurrent_single_use_first_request_wins(self, db_session):
        """
        Gherkin: Two devices apply the same single-use voucher simultaneously.
        Exactly one succeeds (HTTP 200); the other gets HTTP 409.

        PADLOCK P4 — Concurrent use: exactly 1 success via DB-level atomic check.
        """
        from services.voucher_service import apply_voucher

        results = []
        lock = threading.Lock()

        def attempt():
            cart    = build_cart(total_egp=120.00)
            voucher = build_voucher(percent_discount=10)
            try:
                r = apply_voucher(cart, voucher, db=db_session)
                with lock:
                    results.append(("ok", r))
            except Exception as e:
                with lock:
                    results.append(("err", e))

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = [r for tag, r in results if tag == "ok"]
        conflicts = [r for tag, r in results if tag == "err"]

        assert len(successes) == 1, "Exactly one request must succeed"  # P4
        assert len(conflicts) == 1, "Exactly one request must get 409"


# ---------------------------------------------------------------------------
# FR13 — Voucher Stacking Rejected
# ---------------------------------------------------------------------------

def test_voucher_stacking_rejected_with_specific_error_code(db_session):
    """
    PADLOCK P3 — VOUCHER_STACK_REJECTED code, not a generic 422.
    Cart that already has a voucher rejects a second one.
    """
    from services.voucher_service import apply_voucher, VoucherError
    cart = build_cart(total_egp=100.00)
    cart.voucher_applied = True  # first voucher already on cart

    with pytest.raises(VoucherError) as exc_info:
        apply_voucher(cart, build_voucher(percent_discount=10), db=db_session)

    assert exc_info.value.code == "VOUCHER_STACK_REJECTED"  # P3
