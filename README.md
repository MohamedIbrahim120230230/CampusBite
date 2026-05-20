# 🍽️ CampusBite

### University Cafeteria Ordering System

> Order smarter. Eat better. Built for campus life.

![Status](https://img.shields.io/badge/status-in%20development-yellow)
![Stack](https://img.shields.io/badge/stack-React%20%7C%20FastAPI%20%7C%20PostgreSQL%20%7C%20Redis-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 📌 What is CampusBite?

CampusBite is a full-stack university cafeteria ordering platform that lets students browse the menu, build a cart, apply vouchers, and place orders — all from their phone or desktop. Staff manage order fulfilment in real time, and administrators control the entire system from a dedicated panel.

Built as a vertical-slice team project for CSE323 at EJUST, with each member owning a complete feature slice from database to UI.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔐 Authentication | University email login, JWT sessions, brute-force protection, account lockout |
| 🍔 Menu & Cart | Browse by category, full-text search, add to cart, apply vouchers |
| 📦 Order Placement | Real-time stock checks, idempotent order submission, overload circuit breaker |
| 💳 Payment | Online (card/gateway), Cash on collection, Wallet, and Meal Plan support |
| 🔄 Order Lifecycle | Full state machine: PLACED → CONFIRMED → PREPARING → READY → COLLECTED |
| 💸 Refunds | Automatic refund triggers with immutable audit trail |
| ⭐ Feedback | Star ratings and optional text reviews per completed order |
| ⚙️ Admin Panel | Full system control — users, menu, reports, stock, system config |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────┐
│                  Frontend                   │
│           React + Vite (npm run dev)        │
│  Menu │ Cart │ Orders │ Admin │ Tracking    │
└────────────────────┬────────────────────────┘
                     │ HTTP / REST
┌────────────────────▼────────────────────────┐
│                Backend API                  │
│         Python + FastAPI (uvicorn)          │
│ Auth │ Menu │ Orders │ Payment │ Lifecycle  │
└──────────┬─────────────────────┬────────────┘
           │                     │
┌──────────▼──────────┐ ┌────────▼────────────┐
│     PostgreSQL       │ │        Redis         │
│  Main data store     │ │  Sessions • Stock    │
│  (port 5432)         │ │  locks • Rate limits │
└─────────────────────┘ │  (port 6379)         │
                         └─────────────────────┘
```

---

## 🗂️ Repository Structure

```
CampusBite/
├── backend/               # Python FastAPI application
│   └── main.py            # Entry point (uvicorn main:app)
├── frontend/              # React + Vite application
│   └── package.json
├── database/
│   └── migrations/        # SQL migration files (run in order)
├── docs/                  # SRS, vertical slice breakdown
├── scripts/               # Utility scripts
├── tests/
│   └── auth/              # Auth test suite
└── .gitignore
```

---

## 🛠️ Prerequisites

Make sure all of the following are installed and running before setup:

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.12+ | Backend runtime |
| Node.js | 20+ | Frontend runtime |
| PostgreSQL | 15+ | Primary database (port 5432) |
| Redis | 7+ | Sessions, rate limiting, stock locks (port 6379) |

### Verify Redis is running

```powershell
& "C:\Program Files\Redis\redis-cli.exe" ping
# Expected response: PONG
```

---

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/MohamedIbrahim120230230/CampusBite.git
cd CampusBite
```

### 2. Set up the database

Create the database and run migrations in order:

```bash
set PATH=%PATH%;C:\Program Files\PostgreSQL\18\bin
set PGPASSWORD=postgres123
psql -U postgres -c "CREATE DATABASE cafeteria;"
psql -U postgres -d cafeteria -f database/migrations/001_create_users.sql
psql -U postgres -d cafeteria -f database/migrations/002_create_menu_cart.sql
psql -U postgres -d cafeteria -f database/migrations/003_create_order_payment.sql
psql -U postgres -d cafeteria -f database/migrations/004_create_stock_resilience.sql
psql -U postgres -d cafeteria -f database/migrations/005_create_lifecycle_reports.sql
```
###  3. Run the backend
```

cd C:\Users\Administrator\Downloads\CampusBite\backend

# Set the database connection string
$env:DATABASE_URL = "postgresql://postgres:postgres123@localhost:5432/cafeteria"

# Install dependencies (first time only)
pip install -r requirements.txt

# Start the development server
uvicorn main:app --reload
```

The API will be available at **http://localhost:8000**  
Interactive API docs: **http://localhost:8000/docs**

### 4. Run the frontend

```powershell
cd C:\Users\Administrator\Downloads\CampusBite\frontend

# Install dependencies (first time only)
npm install

# Start the development server
npm run dev
```

The app will be available at **http://localhost:5173**

---

## 🔧 Environment Variables

The backend reads the following environment variables:

| Variable | Example Value | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:postgres123@localhost:5432/cafeteria` | PostgreSQL connection string |

Set them in PowerShell before running the server:

```powershell
$env:DATABASE_URL = "postgresql://postgres:postgres123@localhost:5432/cafeteria"
```

Or create a `.env` file in the `backend/` directory:

```env
DATABASE_URL=postgresql://postgres:postgres123@localhost:5432/cafeteria
```

---

## 📐 UML Class Diagram

```mermaid
classDiagram
    class User {
        +UUID id
        +String email
        +String display_name
        +String password_hash
        +UserRole role
        +UserStatus status
        +Integer failed_attempts
        +DateTime locked_until
        +Decimal wallet_balance
        +Decimal meal_plan_balance
        +DateTime created_at
        +login()
        +logout()
        +resetPassword()
    }

    class MenuItem {
        +Integer id
        +String name
        +String category
        +Decimal price
        +Integer stock_qty
        +Integer max_order_qty
        +Boolean active
        +isAvailable()
        +updateStock()
    }

    class CartSession {
        +Integer id
        +UUID user_id
        +JSONB items
        +DateTime locked_at
        +DateTime updated_at
        +addItem()
        +removeItem()
        +lock()
        +isLocked()
    }

    class Voucher {
        +Integer id
        +String code
        +Decimal discount
        +Decimal min_order
        +DateTime expires_at
        +UUID used_by
        +isValid()
        +isExpired()
        +apply()
    }

    class Order {
        +UUID id
        +UUID user_id
        +JSONB items
        +OrderStatus status
        +String payment_method
        +Decimal total
        +DateTime created_at
        +place()
        +cancel()
        +advance()
    }

    class OrderItem {
        +Integer id
        +UUID order_id
        +Integer menu_item_id
        +Integer quantity
        +Decimal unit_price
        +getSubtotal()
    }

    class Feedback {
        +Integer id
        +UUID order_id
        +UUID user_id
        +Integer rating
        +String comment
        +DateTime created_at
        +submit()
    }

    class PasswordResetToken {
        +Integer id
        +UUID user_id
        +String token
        +DateTime expires_at
        +Boolean used
        +validate()
    }

    User "1" --> "0..*" CartSession : has
    User "1" --> "0..*" Order : places
    User "1" --> "0..*" Feedback : writes
    User "1" --> "0..*" PasswordResetToken : requests
    CartSession "1" --> "0..*" MenuItem : contains
    Order "1" --> "1..*" OrderItem : includes
    OrderItem "0..*" --> "1" MenuItem : references
    Voucher "0..1" --> "0..1" User : used_by
    Feedback "1" --> "1" Order : reviews
```

---

## 👥 Team & Vertical Slice Ownership

Each team member owns one complete vertical slice — database schema through API through UI.

| Member | Slice | Branch | Functional Requirements |
|---|---|---|---|
| Member 1 | Auth & Identity | `feature/auth-identity` | FR01–FR08, FR19–FR20 (admin users/staff) |
| Member 2 | Menu & Cart | `feature/menu-cart` | FR09–FR19, FR52 |
| Member 3 | Order & Payment | `feature/order-payment` | FR20–FR33 |
| Member 4 | Stock & Resilience | `feature/stock-resilience` | FR22, FR24–FR25, FR27–FR29, FR41 |
| Member 5 | Lifecycle & Reports | `feature/lifecycle-reports` | FR34–FR46, FR47–FR56 |

---

## 🗄️ Database Schema (Overview)

```
users               menu_items          orders
─────────────       ──────────────      ──────────────
id (UUID)           id                  id (UUID)
email               name                user_id  → users
password_hash       category            status
role                price               payment_method
active              stock_qty           total_egp
created_at          max_order_qty       idempotency_key
                    active (soft-del)   created_at

order_items         vouchers            stock_locks
─────────────       ──────────────      ──────────────
id                  id                  id
order_id → orders   code                order_id
menu_item_id        discount_type       menu_item_id
quantity            discount_value      locked_qty
unit_price          expires_at          acquired_at
                    min_cart_value      expires_at
                    used_by (jsonb)

payments            refunds             ratings
─────────────       ──────────────      ──────────────
id                  id                  id
order_id            order_id            order_id
gateway_ref         amount              user_id
method              method              stars (1–5)
status              gateway_ref         comment
idempotency_key     status              created_at
created_at          initiated_by
```

---

## 🔌 API Endpoints

### Authentication

| Method | Endpoint | Description | FR |
|---|---|---|---|
| POST | `/api/auth/login` | Login with university email & password | FR01 |
| POST | `/api/auth/logout` | Invalidate all active sessions | FR05 |
| POST | `/api/auth/refresh` | Refresh JWT access token | FR04 |
| POST | `/api/auth/password-reset` | Request password reset link | FR06 |

### Menu & Cart

| Method | Endpoint | Description | FR |
|---|---|---|---|
| GET | `/api/menu` | Browse menu, filter by `?category=` | FR09 |
| GET | `/api/menu/search?q=` | Full-text search | FR10 |
| GET | `/api/cart/{user_id}` | View cart contents | FR12 |
| POST | `/api/cart/{user_id}/add` | Add item to cart | FR11 |
| PUT | `/api/cart/{user_id}/item/{id}` | Update item quantity | FR12 |
| DELETE | `/api/cart/{user_id}/item/{id}` | Remove item from cart | FR12 |
| POST | `/api/cart/{user_id}/voucher` | Apply voucher code | FR13 |
| POST | `/api/cart/{user_id}/lock` | Lock cart at checkout | FR17 |

### Orders & Payment

| Method | Endpoint | Description | FR |
|---|---|---|---|
| POST | `/api/orders` | Place order | FR20 |
| GET | `/api/orders/{order_id}` | Get order details | FR36 |
| GET | `/api/orders/{order_id}/track` | Real-time status (SSE) | FR36 |
| POST | `/api/orders/{order_id}/pay` | Submit payment | FR27 |
| POST | `/api/orders/{order_id}/cancel` | Cancel order | FR37 |
| POST | `/api/webhooks/payment` | Payment gateway webhook | FR27 |

### Admin

| Method | Endpoint | Description | FR |
|---|---|---|---|
| GET | `/api/admin/users` | List all users | FR50 |
| PUT | `/api/admin/users/{id}/role` | Update user role | FR07 |
| POST | `/api/admin/menu` | Create menu item | FR18, FR52 |
| PUT | `/api/admin/menu/{id}` | Update menu item | FR18 |
| DELETE | `/api/admin/menu/{id}` | Soft-delete menu item | FR18 |
| GET | `/api/admin/reports` | Revenue and order reports | FR53 |
| GET | `/api/admin/orders/flagged` | Review queue for flagged orders | FR24, FR56 |

---

## ⚠️ Edge Cases Implemented

| FR | Description |
|---|---|
| FR03 | Account locked for 15 min after 5 failed login attempts |
| FR04 | Session expires after 30 min inactivity; token invalidated server-side |
| FR14 | Voucher rejected if expired, already used by this user, or below minimum cart value |
| FR15 | Voucher stacking rejected with clear error |
| FR16 | Cart total floored at 0 on over-discount — no negative totals |
| FR17 | Cart locked read-only once checkout begins; user notified of any price/stock changes |
| FR22 | Pessimistic stock lock (SELECT FOR UPDATE) during payment processing (10 min TTL) |
| FR23 | Duplicate order detection within 60-second window using idempotency keys |
| FR24 | Orders exceeding quantity/value thresholds routed to admin review queue |
| FR25 | HTTP 503 + Retry-After when concurrent order count exceeds load threshold |
| FR28 | Stock lock released and retry presented on payment gateway failure |
| FR29 | Transaction cancelled and stock released on gateway timeout (> 10s) |
| FR30 | Gateway-level idempotency key prevents double-charging on retries |
| FR32 | Wallet debit executed atomically; order not confirmed if debit fails |
| FR37 | Cancellation window enforced server-side (2 min from placement) |
| FR40 | Abandoned checkouts auto-cancelled after 10 min; stock locks released |
| FR41 | Post-confirmation stock inconsistency triggers admin notification |

---

## 📋 Requirements Coverage

**56** Functional Requirements · **24** Edge Cases · **32** Non-Functional Requirements

See the [`docs/`](./docs) folder for:
- `cafeteria_requirements_v2.docx` — Full SRS (v2.0, production-ready)
- `Software_phase1_2.docx` — Phase 1 actor analysis, hidden requirements, and Gherkin test scenarios
- `vertical_slice_cafeteria.html` — Interactive vertical slice breakdown

---

## 🧪 Running Tests

```bash
# From the repo root
pytest tests/
```

## 🧪 Automated Test Report

This project implements a rigorous automated testing suite using `pytest` to guarantee the integrity, security, and performance of both backend services and frontend business logic. 

### 📊 Test Suite Summary

| Target Domain | Test Context | Code Coverage | Status |
| :--- | :--- | :---: | :---: |
| **Authentication & Access Control** | Integration Endpoints & JWT Security | Core Auth Modules | **PASSED** |
| **Academic Domain Rules** | University Email & ID Detection Logic | Business Invariants | **PASSED** |
| **Order & Payment Processing** | Idempotency, Callbacks, & Integrity | Financial Workflows | **PASSED** |
| **Inventory & Stock Safeguards** | Load-shedding & Race-condition TTLs | System Stability | **PASSED** |
| **Client-Side Form Validation** | Egyptian Formats, Cards, & Strength | UI/UX Core Utilities | **PASSED** |

---

### 🔍 Verified System Features

#### 🔒 1. Authentication & Security (Integration & Unit)
* **Secure Session Handshakes:** Validated successful token distribution (`access` and `refresh`) on legitimate login requests.
* **Robust Access Boundaries:** Strict protection over public vs. admin endpoints (e.g., verifying `401 Unauthorized` for missing tokens, `403 Forbidden` for inadequate roles).
* **Defensive Lockout System:** Successfully tested anti-brute-force features, verifying that user accounts lock automatically for exactly `900s` after max invalid attempts are reached.
* **Account Life-cycle Verification:** Handled clean rejections and dedicated warning messages for suspended, locked, or unrecognized profiles.
* **Cryptographic Invariants:** Confirmed that passwords are deterministically hashed via non-plaintext unique salts, and verified JWT preservation of custom token claims.

#### 🎓 2. University Domain Logic
* **Domain Restraints:** Strict regex validation ensuring only recognized institutional domains (e.g., `@ejust.edu.eg`) pass the user registration schema.
* **Automatic Role Parsing:** Validated high-accuracy detection separating *Student* accounts (matched via standard numeric suffixes/6-digit patterns) from *Staff* accounts.
* **Sanitization Filters:** Assured input tolerance tests pass for trailing/leading whitespaces and case-insensitivity on registration formats.

#### 🛒 3. Order Processing & Integration Engines
* **Strict Financial Constraints:** Verified that empty carts return immediate validation failures (`400 Bad Request`) and system overloads yield a graceful `503 Service Unavailable`.
* **Idempotency Protection:** Proved that duplicated network submissions containing identical idempotency keys safely return existing order snapshots instead of generating multiple charges.
* **State-Machine Assertions:** Successfully simulated order cancellation rules—allowing standard refunds within the configured `15-minute` grace window while throwing expected conflicts (`409`) on finalized or completed packages.
* **Payment Gateway Handlers:** Emulated mock asynchronous webhooks confirming correct state transitions upon immediate cash or successful third-party payment provider callbacks.

#### 📦 4. Stock & Inventory Control
* **OOS (Out of Stock) Prevention:** Guaranteed race-condition prevention by rejecting line item requests exceeding available quantities.
* **Stock TTL Reservations:** Verified the temporary stock locking engine maintains a reliable `10-minute` Time-to-Live window to hold checkout items securely without causing stale data leaks.
* **Bulk Protection:** Enforced safety caps limiting maximum order units per customer to `20` items to inhibit bulk abuse.

#### 💻 5. Frontend Client-Side Verification
* **Cardholder Security Metrics:** Verified Luhn-adjacent string checking formats for 16-digit payment cards, space strip tolerances, CVV length caps, and accurate expiration month boundaries.
* **Localization Formatting:** Assured local validation compliance for Egyptian cellular providers (matching `010`, `011`, `012`, `015` string lengths).
* **Smart Voucher Engine:** Verified complex discount application rules, proving that flat voucher codes cap out gracefully at subtotal ceilings and that usage metrics accurately decay based on absolute expiration configurations.
---

## 📄 License

MIT — see [LICENSE](./LICENSE) for details.

---

Built with ☕ by the CSE323 Team — EJUST 2026
