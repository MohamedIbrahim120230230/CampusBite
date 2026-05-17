-- ============================================================
-- CSE323 Cafeteria System - PostgreSQL Schema Migration
-- Run this on your PostgreSQL database:
--   psql -U cafeteria_user -d cafeteria_db -f 001_order_payment_schema.sql
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── MENU ITEMS ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS menu_items (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(120) NOT NULL,
    description     TEXT,
    price           NUMERIC(10,2) NOT NULL,
    category        VARCHAR(60),
    image_url       VARCHAR(255),
    is_available    BOOLEAN NOT NULL DEFAULT TRUE,
    stock_count     INTEGER NOT NULL DEFAULT 0,
    reserved_count  INTEGER NOT NULL DEFAULT 0,  -- FR29: stock lock
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_menu_category ON menu_items(category);
CREATE INDEX IF NOT EXISTS idx_menu_available ON menu_items(is_available);

-- ── VOUCHERS ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vouchers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code            VARCHAR(50) NOT NULL UNIQUE,  -- indexed for fast lookup
    discount_type   VARCHAR(20),                  -- flat | percent | free_delivery
    discount_value  NUMERIC(10,2) DEFAULT 0,
    min_order       NUMERIC(10,2) DEFAULT 0,
    max_uses        INTEGER DEFAULT 1,
    used_count      INTEGER DEFAULT 0,
    expires_at      TIMESTAMPTZ,
    is_active       BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_voucher_code ON vouchers(code);

-- ── CARTS ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS carts (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     VARCHAR(36) NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cart_user ON carts(user_id);

CREATE TABLE IF NOT EXISTS cart_items (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cart_id         UUID NOT NULL REFERENCES carts(id) ON DELETE CASCADE,
    menu_item_id    UUID NOT NULL REFERENCES menu_items(id),
    quantity        INTEGER NOT NULL DEFAULT 1
);

-- ── ORDERS ────────────────────────────────────────────────────
CREATE TYPE order_status AS ENUM (
    'pending_payment',
    'confirmed',
    'preparing',
    'ready_for_pickup',
    'delivered',
    'cancelled',
    'payment_timeout'
);

CREATE TYPE payment_method AS ENUM (
    'online',
    'cash',
    'wallet',
    'meal_plan'
);

CREATE TABLE IF NOT EXISTS orders (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- FR31: idempotency key prevents duplicate orders
    idempotency_key  VARCHAR(100) NOT NULL UNIQUE,
    user_id          VARCHAR(36) NOT NULL,
    status           order_status NOT NULL DEFAULT 'pending_payment',
    payment_method   payment_method,
    subtotal         NUMERIC(10,2) NOT NULL,
    discount         NUMERIC(10,2) NOT NULL DEFAULT 0,
    total            NUMERIC(10,2) NOT NULL,
    voucher_id       UUID REFERENCES vouchers(id),
    voucher_code     VARCHAR(50),
    notes            TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW(),
    confirmed_at     TIMESTAMPTZ,
    cancelled_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_order_user   ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_order_status ON orders(status);
-- FR31: unique idempotency_key already indexed via UNIQUE constraint

CREATE TABLE IF NOT EXISTS order_items (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id        UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    menu_item_id    UUID NOT NULL REFERENCES menu_items(id),
    name            VARCHAR(120) NOT NULL,   -- snapshot at order time
    unit_price      NUMERIC(10,2) NOT NULL,
    quantity        INTEGER NOT NULL,
    subtotal        NUMERIC(10,2) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);

-- ── PAYMENTS ──────────────────────────────────────────────────
CREATE TYPE payment_status AS ENUM (
    'pending',
    'success',
    'failed',
    'timeout',
    'refunded',
    'indeterminate'
);

CREATE TABLE IF NOT EXISTS payments (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id         UUID NOT NULL REFERENCES orders(id),
    method           payment_method NOT NULL,
    status           payment_status NOT NULL DEFAULT 'pending',
    amount           NUMERIC(10,2) NOT NULL,
    transaction_id   VARCHAR(120) UNIQUE,      -- from payment gateway
    gateway_response JSONB,                    -- full gateway payload
    failure_reason   VARCHAR(255),
    refund_amount    NUMERIC(10,2),
    refund_ref       VARCHAR(120),
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW(),
    timeout_at       TIMESTAMPTZ               -- FR24: payment timeout deadline
);

CREATE INDEX IF NOT EXISTS idx_payment_order  ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_payment_status ON payments(status);
-- FR24: index for background timeout job
CREATE INDEX IF NOT EXISTS idx_payment_timeout ON payments(timeout_at) WHERE status = 'pending';

-- ── SEED DATA ─────────────────────────────────────────────────
INSERT INTO menu_items (name, description, price, category, is_available, stock_count)
VALUES
    ('Beef Burger',       'Grilled beef patty with fresh toppings', 45.00, 'Main',    TRUE, 50),
    ('Veggie Burger',     'Plant-based patty with cheese',          38.00, 'Main',    TRUE, 30),
    ('Salad Bowl',        'Mixed greens with olive oil dressing',   25.00, 'Salads',  TRUE, 40),
    ('Salad Wrap',        'Grilled chicken in tortilla wrap',       30.00, 'Salads',  TRUE, 35),
    ('Water Bottle',      'Still mineral water 500ml',               5.00, 'Drinks',  TRUE, 200),
    ('Orange Juice',      'Fresh squeezed orange juice',            20.00, 'Drinks',  TRUE, 60),
    ('Fish Sandwich',     'Crispy fish with tartar sauce',          40.00, 'Main',    FALSE, 0),
    ('Grilled Chicken',   'Herb-marinated grilled chicken breast',  50.00, 'Main',    TRUE, 25)
ON CONFLICT DO NOTHING;

INSERT INTO vouchers (code, discount_type, discount_value, min_order, max_uses, expires_at, is_active)
VALUES
    ('SAVE20',    'flat',    20.00, 50.00,  100, NOW() + INTERVAL '30 days', TRUE),
    ('HALF50',    'percent', 50.00, 100.00,  50, NOW() + INTERVAL '30 days', TRUE),
    ('FREESHIP',  'free_delivery', 0.00, 0.00, 500, NOW() + INTERVAL '60 days', TRUE)
ON CONFLICT DO NOTHING;
