"""
Unit Tests — FR17, FR19
Cart lock at checkout & max order quantity per item.
"""
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def db_session():
    return MagicMock()


# ---------------------------------------------------------------------------
# TDP-M2-02 — FR17 Cart Lock at Checkout
# ---------------------------------------------------------------------------

class TestCartLock:

    def test_locked_cart_rejects_all_mutations(self, db_session):
        """
        PADLOCK P1 — Locked cart rejects all mutations:
          HTTP 409 CART_LOCKED on any POST/PATCH to cart.
        """
        from services.cart_service import CartService
        svc  = CartService(db_session)
        cart = svc.create_and_lock_cart(user_id="user-001")

        result = svc.add_item(cart_id=cart.id, item_id="item-xyz", quantity=1)
        assert result.http_status == 409       # P1
        assert result.error       == "CART_LOCKED"  # P1

    def test_locked_cart_rejects_remove_item(self, db_session):
        """PADLOCK P1 — Remove-item also blocked on locked cart."""
        from services.cart_service import CartService
        svc  = CartService(db_session)
        cart = svc.create_and_lock_cart(user_id="user-001")

        result = svc.remove_item(cart_id=cart.id, item_id="item-xyz")
        assert result.http_status == 409
        assert result.error       == "CART_LOCKED"

    def test_price_change_detected_and_reported_on_lock(self, db_session):
        """
        PADLOCK P2 — Price drift detected and reported:
          warnings[] must contain old_price and new_price fields.
        """
        from services.cart_service import CartService
        svc  = CartService(db_session)
        cart = svc.build_cart_with_item("koshary", price_at_add=35.00)
        svc.change_item_price("koshary", new_price=40.00)

        result = svc.lock_cart_for_checkout(cart_id=cart.id)
        assert result.warnings is not None            # P2
        warning = result.warnings[0]
        assert warning["old_price"] == 35.00          # P2
        assert warning["new_price"] == 40.00          # P2

    def test_stock_depletion_blocks_cart_locking(self, db_session):
        """
        PADLOCK P3 — Stock depletion blocks locking:
          HTTP 409 if any item reaches 0 stock before lock completes.
        """
        from services.cart_service import CartService
        svc = CartService(db_session)
        cart = svc.build_cart_with_item("koshary", price_at_add=35.00)
        svc.set_item_stock("koshary", quantity=0)  # deplete stock

        result = svc.lock_cart_for_checkout(cart_id=cart.id)
        assert result.http_status == 409


# ---------------------------------------------------------------------------
# TDP-M2-03 — FR19 Max Order Quantity Per Item
# ---------------------------------------------------------------------------

class TestMaxOrderQuantity:

    def test_quantity_at_cap_is_accepted(self, db_session):
        """
        PADLOCK P1 — Cap is per-item, not per-cart.
        Quantity == max is accepted.
        """
        from services.cart_service import CartService
        svc = CartService(db_session)
        svc.set_item_max_qty("grilled_chicken", max_qty=10)

        result = svc.add_item(cart_id="cart-001", item_id="grilled_chicken", quantity=10)
        assert result.http_status == 200  # at cap → accepted

    def test_quantity_one_above_cap_is_rejected(self, db_session):
        """
        PADLOCK P2 — Response includes max_allowed so the client can display correct UI.
        PADLOCK P1 — Cap enforcement.
        """
        from services.cart_service import CartService
        svc = CartService(db_session)
        svc.set_item_max_qty("grilled_chicken", max_qty=10)

        result = svc.add_item(cart_id="cart-001", item_id="grilled_chicken", quantity=11)
        assert result.http_status == 422                         # above cap → rejected
        assert result.error       == "QUANTITY_EXCEEDS_CAP"     # exact error code
        assert result.max_allowed == 10                         # P2 — client needs this

    def test_cap_is_per_item_not_per_cart(self, db_session):
        """
        PADLOCK P1 — 10 of item A + 10 of item B = 20 total → allowed.
          Cap applies per individual item, not to the cart total.
        """
        from services.cart_service import CartService
        svc = CartService(db_session)
        svc.set_item_max_qty("grilled_chicken", max_qty=10)
        svc.set_item_max_qty("koshary",         max_qty=10)

        result = svc.add_multiple_items(
            cart_id="cart-001",
            items=[("grilled_chicken", 10), ("koshary", 10)]
        )
        assert result.http_status == 200  # P1 — 20 total but 10 each → OK

    def test_cap_enforced_at_add_to_cart(self, db_session):
        """
        PADLOCK P3 — Cap enforced at add-to-cart AND checkout (both checkpoints).
        This test covers the add-to-cart gate.
        """
        from services.cart_service import CartService
        svc = CartService(db_session)
        svc.set_item_max_qty("grilled_chicken", max_qty=5)

        result = svc.add_item(cart_id="cart-001", item_id="grilled_chicken", quantity=6)
        assert result.http_status == 422  # P3 — gate 1

    def test_cap_enforced_at_checkout(self, db_session):
        """
        PADLOCK P3 — Cap enforced at add-to-cart AND checkout.
        This test covers the checkout gate (in case cap changed between add and checkout).
        """
        from services.cart_service import CartService
        svc = CartService(db_session)
        # Add item when cap is 10
        cart = svc.add_item(cart_id="cart-001", item_id="grilled_chicken", quantity=10)
        # Admin lowers cap to 5 after item was already in cart
        svc.set_item_max_qty("grilled_chicken", max_qty=5)

        result = svc.lock_cart_for_checkout(cart_id="cart-001")
        assert result.http_status == 422  # P3 — gate 2 catches the now-over-cap quantity
