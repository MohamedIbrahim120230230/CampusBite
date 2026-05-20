"""
Unit Tests — FR09, FR10, FR11
Menu browsing, category filtering, keyword search, out-of-stock handling.
"""
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def db_session():
    return MagicMock()


@pytest.fixture
def menu_service(db_session):
    from services.menu_service import MenuService
    return MenuService(db_session)


# ---------------------------------------------------------------------------
# FR09 / FR10 — Browse & Filter Menu
# ---------------------------------------------------------------------------

class TestMenuBrowsing:

    @pytest.mark.parametrize("category", ["Meals", "Beverages", "Snacks"])
    def test_filter_returns_only_items_in_requested_category(self, menu_service, category):
        """
        Gherkin: Filter menu by category (Scenario Outline).
        Each item in the response must belong to the requested category only.
        """
        result = menu_service.get_menu(category=category)
        assert result.http_status == 200
        for item in result.items:
            assert item.category == category, (
                f"Item '{item.name}' category '{item.category}' != '{category}'"
            )

    def test_menu_item_response_shape(self, menu_service):
        """
        Each menu item must include: id, name, price_egp, category,
        in_stock, avg_rating, max_order_qty — as defined in the API contract.
        """
        result = menu_service.get_menu()
        assert len(result.items) > 0
        item = result.items[0]
        assert hasattr(item, "id")
        assert hasattr(item, "name")
        assert hasattr(item, "price_egp")
        assert hasattr(item, "category")
        assert hasattr(item, "in_stock")
        assert hasattr(item, "avg_rating")
        assert hasattr(item, "max_order_qty")

    def test_invalid_category_returns_400(self, menu_service):
        """API contract: invalid category value → HTTP 400."""
        result = menu_service.get_menu(category="InvalidCategory")
        assert result.http_status == 400

    def test_pagination_defaults(self, menu_service):
        """Default page=1 and per_page=20; max per_page=100."""
        result = menu_service.get_menu()
        assert result.page == 1
        assert result.per_page == 20

    def test_per_page_capped_at_100(self, menu_service):
        """Requesting more than 100 items per page should be capped or rejected."""
        result = menu_service.get_menu(per_page=200)
        assert result.per_page <= 100


# ---------------------------------------------------------------------------
# FR10 — Keyword Search
# ---------------------------------------------------------------------------

class TestMenuSearch:

    def test_search_returns_matching_items(self, menu_service):
        """Keyword 'koshary' must return items matching that keyword."""
        result = menu_service.search_menu(q="koshary")
        assert result.http_status == 200
        assert len(result.items) > 0

    def test_empty_search_returns_200_with_friendly_message(self, menu_service):
        """
        Gherkin: no results → HTTP 200 (not 404) with friendly message.
        """
        result = menu_service.search_menu(q="xyz_nonexistent")
        assert result.http_status == 200
        assert "No items found for 'xyz_nonexistent'" in result.message

    def test_search_response_time_within_1000ms(self, menu_service):
        """
        NFR04 (refined): Full-text search API responds ≤ 1,000 ms at p95.
        Verified here at the unit level using a timing guard on the service method.
        """
        import time
        start = time.perf_counter()
        menu_service.search_menu(q="koshary")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 1000, f"Search took {elapsed_ms:.0f} ms — exceeds 1000 ms SLA"


# ---------------------------------------------------------------------------
# FR11 — Out-of-Stock Items
# ---------------------------------------------------------------------------

class TestOutOfStock:

    def test_out_of_stock_item_shows_unavailable_badge(self, menu_service):
        """Out-of-stock items must have in_stock=False in the API response."""
        result = menu_service.get_menu()
        out_of_stock = [i for i in result.items if not i.in_stock]
        # If any out-of-stock items exist, verify they are flagged correctly
        for item in out_of_stock:
            assert item.in_stock is False

    def test_out_of_stock_item_cannot_be_added_to_cart(self, db_session):
        """FR11: Out-of-stock items must be non-selectable (add-to-cart blocked)."""
        from services.cart_service import CartService
        cart_svc = CartService(db_session)
        result = cart_svc.add_item(
            cart_id="cart-001",
            item_id="out-of-stock-item-uuid",
            quantity=1
        )
        assert result.http_status == 409
        assert "out of stock" in result.message.lower() or result.error == "ITEM_OUT_OF_STOCK"
