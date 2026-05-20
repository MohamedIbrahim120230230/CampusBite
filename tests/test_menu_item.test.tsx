/**
 * Frontend Unit Tests — FR11
 * Out-of-stock badge rendering and add-to-cart button state.
 *
 * Tool: Vitest + React Testing Library
 * Run:  npm run test
 */

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MenuItem } from '@/components/MenuItem';


// ---------------------------------------------------------------------------
// FR11 — Out-of-Stock Items Non-Selectable
// ---------------------------------------------------------------------------

describe('MenuItem — out of stock', () => {

  it('shows "Out of Stock" badge when in_stock is false', () => {
    render(
      <MenuItem
        id="item-001"
        name="Koshary"
        price_egp={35}
        category="Meals"
        in_stock={false}
        avg_rating={4.2}
        max_order_qty={10}
      />
    );
    expect(screen.getByText(/out of stock/i)).toBeInTheDocument();
  });

  it('disables the add-to-cart button when in_stock is false', () => {
    render(
      <MenuItem
        id="item-001"
        name="Koshary"
        price_egp={35}
        category="Meals"
        in_stock={false}
        avg_rating={4.2}
        max_order_qty={10}
      />
    );
    const addButton = screen.getByRole('button', { name: /add to cart/i });
    expect(addButton).toBeDisabled();
  });

  it('does NOT show out-of-stock badge when item is in stock', () => {
    render(
      <MenuItem
        id="item-002"
        name="Burger"
        price_egp={55}
        category="Meals"
        in_stock={true}
        avg_rating={4.5}
        max_order_qty={5}
      />
    );
    expect(screen.queryByText(/out of stock/i)).not.toBeInTheDocument();
  });

  it('enables add-to-cart button when item is in stock', () => {
    render(
      <MenuItem
        id="item-002"
        name="Burger"
        price_egp={55}
        category="Meals"
        in_stock={true}
        avg_rating={4.5}
        max_order_qty={5}
      />
    );
    const addButton = screen.getByRole('button', { name: /add to cart/i });
    expect(addButton).not.toBeDisabled();
  });

  it('prevents click events on out-of-stock add-to-cart button', () => {
    const mockAddToCart = vi.fn();
    render(
      <MenuItem
        id="item-001"
        name="Koshary"
        price_egp={35}
        category="Meals"
        in_stock={false}
        avg_rating={4.2}
        max_order_qty={10}
        onAddToCart={mockAddToCart}
      />
    );
    const addButton = screen.getByRole('button', { name: /add to cart/i });
    fireEvent.click(addButton);
    expect(mockAddToCart).not.toHaveBeenCalled();
  });

});


// ---------------------------------------------------------------------------
// MenuItem — General Display
// ---------------------------------------------------------------------------

describe('MenuItem — display', () => {

  const baseProps = {
    id:           'item-003',
    name:         'Grilled Chicken',
    price_egp:    65,
    category:     'Meals',
    in_stock:     true,
    avg_rating:   null,
    max_order_qty: 8,
  };

  it('renders item name', () => {
    render(<MenuItem {...baseProps} />);
    expect(screen.getByText('Grilled Chicken')).toBeInTheDocument();
  });

  it('renders price in EGP', () => {
    render(<MenuItem {...baseProps} />);
    expect(screen.getByText(/65/)).toBeInTheDocument();
  });

  it('renders category', () => {
    render(<MenuItem {...baseProps} />);
    expect(screen.getByText(/Meals/i)).toBeInTheDocument();
  });

  it('shows no rating when avg_rating is null', () => {
    render(<MenuItem {...baseProps} avg_rating={null} />);
    expect(screen.queryByText(/stars/i)).not.toBeInTheDocument();
  });

  it('shows star rating when avg_rating is provided', () => {
    render(<MenuItem {...baseProps} avg_rating={4.2} />);
    expect(screen.getByText(/4\.2/)).toBeInTheDocument();
  });

});


// ---------------------------------------------------------------------------
// MenuItem — Quantity Cap Display (FR19)
// ---------------------------------------------------------------------------

describe('MenuItem — quantity cap', () => {

  it('limits quantity input to max_order_qty', () => {
    render(
      <MenuItem
        id="item-004"
        name="Juice"
        price_egp={20}
        category="Beverages"
        in_stock={true}
        avg_rating={null}
        max_order_qty={3}
      />
    );
    const qtyInput = screen.getByRole('spinbutton');
    expect(qtyInput).toHaveAttribute('max', '3');
  });

});
