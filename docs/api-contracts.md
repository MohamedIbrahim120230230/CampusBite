# API Contracts — University Cafeteria Ordering System
**Version:** 1.0  
**Stack:** UI → React + Bootstrap CSS · Logic → Python (FastAPI) · DB → PostgreSQL  
**Last updated:** 2026-05-09  
**Owner:** Member 1 (Lead) — update this file via PR; all members must approve changes.

---

## How to use this document

1. **Before writing any cross-slice call**, find the contract here and match the request/response shape exactly.
2. **If your slice isn't ready yet**, the calling member mocks the endpoint using the shape below — no blocked work.
3. **Never change a contract unilaterally.** Open a PR, tag all five members, get at least two approvals.
4. **All endpoints are prefixed** with `/api/v1` unless marked otherwise.
5. **All timestamps** are ISO 8601 UTC strings: `"2026-05-09T12:00:00Z"`.
6. **All IDs** are UUID v4 strings.

---

## Standard response envelope

Every endpoint — success or error — returns this envelope. Never return a naked object.

```python
# backend/shared/response.py  (Member 1 creates this on Day 1, everyone imports it)

from fastapi.responses import JSONResponse

def ok(data, status: int = 200):
    return JSONResponse({"success": True, "data": data}, status_code=status)

def err(code: str, message: str, details=None, status: int = 400):
    return JSONResponse(
        {"success": False, "error": {"code": code, "message": message, "details": details}},
        status_code=status
    )
```

```jsonc
// Success shape
{
  "success": true,
  "data": { }          // the actual payload
}

// Error shape
{
  "success": false,
  "error": {
    "code": "ACCOUNT_LOCKED",        // machine-readable constant — use these in React switch/case
    "message": "Account locked for 14 more minutes.",
    "details": { "unlocks_at": "2026-05-09T12:14:00Z" }   // optional extra context
  }
}
```

---

## Authentication header

Every protected endpoint requires:

```
Authorization: Bearer <jwt_token>
```

React helper (put in `frontend/shared/api.js`):

```js
// frontend/shared/api.js
const BASE = "/api/v1";

export async function apiFetch(path, options = {}) {
  const token = localStorage.getItem("jwt_token");
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  const json = await res.json();
  if (!res.ok) throw json.error;   // throw the error object so catch blocks get {code, message}
  return json.data;
}
```

Python decorator (put in `backend/shared/auth.py`):

```python
# backend/shared/auth.py  — Member 1 owns this; everyone imports it
from functools import wraps
from fastapi import Request, HTTPException
import jwt, os

SECRET = os.environ["JWT_SECRET"]

def require_auth(*allowed_roles):
    """Usage: @require_auth("student", "staff", "admin")"""
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            token = request.headers.get("Authorization", "").removeprefix("Bearer ")
            try:
                payload = jwt.decode(token, SECRET, algorithms=["HS256"])
            except jwt.ExpiredSignatureError:
                raise HTTPException(401, "TOKEN_EXPIRED")
            except jwt.InvalidTokenError:
                raise HTTPException(401, "TOKEN_INVALID")
            if allowed_roles and payload["role"] not in allowed_roles:
                raise HTTPException(403, "FORBIDDEN")
            request.state.user = payload
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator
```

---

## Error code registry

All `code` values used across slices. React components switch on these.

| Code | HTTP | Meaning | Slice that raises it |
|---|---|---|---|
| `TOKEN_EXPIRED` | 401 | JWT has expired | Auth (M1) |
| `TOKEN_INVALID` | 401 | JWT malformed or tampered | Auth (M1) |
| `FORBIDDEN` | 403 | Role not permitted for this action | Auth (M1) |
| `ACCOUNT_LOCKED` | 403 | Too many failed logins | Auth (M1) |
| `ACCOUNT_SUSPENDED` | 403 | University account inactive | Auth (M1) |
| `ITEM_UNAVAILABLE` | 409 | Item out of stock at order time | Stock (M4) |
| `STOCK_LOCK_FAILED` | 409 | Could not acquire lock (race) | Stock (M4) |
| `DUPLICATE_ORDER` | 409 | Idempotency key already used | Order (M3) |
| `ORDER_NOT_CANCELLABLE` | 409 | Order past cancellation window | Lifecycle (M5) |
| `INVALID_STATE_TRANSITION` | 409 | Illegal state machine move | Lifecycle (M5) |
| `VOUCHER_INVALID` | 422 | Voucher code not found | Menu/Cart (M2) |
| `VOUCHER_EXPIRED` | 422 | Voucher past expiry date | Menu/Cart (M2) |
| `VOUCHER_ALREADY_USED` | 422 | Voucher used by this user | Menu/Cart (M2) |
| `INSUFFICIENT_BALANCE` | 422 | Wallet/Meal Plan too low | Order (M3) |
| `PAYMENT_FAILED` | 502 | Gateway returned failure | Order (M3) |
| `PAYMENT_TIMEOUT` | 504 | Gateway did not respond in 10s | Order (M3) |
| `SYSTEM_OVERLOADED` | 503 | Circuit breaker open | Order (M3) |

---

## Contract 1 — Auth → everyone

**Owner:** Member 1  
**Used by:** All slices on every protected request

### `POST /api/v1/auth/login`

```jsonc
// Request
{ "email": "ahmed@university.edu", "password": "••••••••" }

// Response 200
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800,          // seconds
  "user": {
    "id": "uuid",
    "email": "ahmed@university.edu",
    "role": "student",          // "student" | "staff" | "admin"
    "display_name": "Ahmed"
  }
}
```

```python
# backend/auth/routes.py  (Member 1)
from fastapi import APIRouter
from backend.shared.response import ok, err

router = APIRouter(prefix="/auth")

@router.post("/login")
async def login(body: LoginRequest):
    user = await verify_university_credentials(body.email, body.password)
    if not user:
        await increment_failed_attempts(body.email)   # FR03
        return err("INVALID_CREDENTIALS", "Email or password incorrect.", status=401)
    if user.locked_until and user.locked_until > now():
        return err("ACCOUNT_LOCKED", "Too many failed attempts.", {"unlocks_at": user.locked_until}, status=403)
    if user.status != "active":
        return err("ACCOUNT_SUSPENDED", "Your university account is not active.", status=403)
    token = create_jwt(user)
    return ok({"access_token": token, "user": user.to_dict()})
```

```jsx
// frontend/auth/Login.jsx  (Member 1)
import { apiFetch } from "../shared/api";

async function handleLogin(email, password) {
  try {
    const data = await apiFetch("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    localStorage.setItem("jwt_token", data.access_token);
    redirectByRole(data.user.role);
  } catch (err) {
    if (err.code === "ACCOUNT_LOCKED") showLockoutTimer(err.details.unlocks_at);
    else if (err.code === "ACCOUNT_SUSPENDED") showSuspendedMessage();
    else showGenericError(err.message);
  }
}
```

### `GET /api/v1/auth/me`

Called by M2/M3/M5 to get current user context.

```jsonc
// Response 200
{
  "id": "uuid",
  "email": "ahmed@university.edu",
  "role": "student",
  "display_name": "Ahmed",
  "wallet_balance": 120.50,
  "meal_plan_balance": 300.00
}
```

```python
# backend/auth/routes.py
@router.get("/me")
@require_auth("student", "staff", "admin")
async def get_me(request: Request):
    user = await get_user_by_id(request.state.user["user_id"])
    return ok(user.to_dict())
```

### `POST /api/v1/auth/logout`

```jsonc
// Response 200
{ "logged_out": true }
```

---

## Contract 2 — Stock lock (M4 owns, M3 calls)

**Owner:** Member 4  
**Called by:** Member 3 (Order/Payment) during order placement

### `POST /api/v1/stock/lock`

Acquire a pessimistic lock on items for payment processing. Lock TTL = 10 minutes.

```jsonc
// Request  (M3 sends this)
{
  "order_id": "uuid",
  "items": [
    { "item_id": "uuid", "quantity": 2 },
    { "item_id": "uuid", "quantity": 1 }
  ]
}

// Response 200 — lock acquired
{
  "locked": true,
  "order_id": "uuid",
  "expires_at": "2026-05-09T12:10:00Z"
}

// Response 409 — one or more items could not be locked
{
  "success": false,
  "error": {
    "code": "STOCK_LOCK_FAILED",
    "message": "Some items are unavailable.",
    "details": {
      "unavailable_items": [
        { "item_id": "uuid", "name": "Koshary", "requested": 2, "available": 0 }
      ]
    }
  }
}
```

```python
# backend/stock/routes.py  (Member 4)
@router.post("/lock")
@require_auth("student")
async def lock_stock(body: LockRequest, request: Request):
    result = await acquire_stock_locks(body.order_id, body.items)
    if not result.success:
        return err("STOCK_LOCK_FAILED", "Some items are unavailable.", result.unavailable, status=409)
    return ok({"locked": True, "order_id": body.order_id, "expires_at": result.expires_at})
```

```jsx
// frontend/order/Checkout.jsx  (Member 3) — mock while M4 not ready
async function acquireStockLock(orderId, cartItems) {
  // MOCK — replace when M4 merges
  // return { locked: true, order_id: orderId, expires_at: new Date(Date.now()+600000).toISOString() };
  return await apiFetch("/stock/lock", {
    method: "POST",
    body: JSON.stringify({ order_id: orderId, items: cartItems }),
  });
}
```

### `DELETE /api/v1/stock/lock/{order_id}`

Release lock on payment failure, timeout, or cancellation.

```jsonc
// Response 200
{ "released": true, "order_id": "uuid" }

// Response 404 — lock not found or already expired
{ "success": false, "error": { "code": "LOCK_NOT_FOUND", "message": "No active lock for this order." } }
```

```python
# backend/stock/routes.py  (Member 4)
@router.delete("/lock/{order_id}")
@require_auth("student", "staff", "admin")
async def release_stock_lock(order_id: str):
    released = await release_locks_for_order(order_id)
    if not released:
        return err("LOCK_NOT_FOUND", "No active lock for this order.", status=404)
    return ok({"released": True, "order_id": order_id})
```

### `POST /api/v1/stock/availability`

Point-in-time availability check (no lock acquired). Called by M2 at add-to-cart and by M3 at order placement.

```jsonc
// Request
{
  "items": [
    { "item_id": "uuid", "quantity": 2 }
  ]
}

// Response 200
{
  "available": true,
  "items": [
    { "item_id": "uuid", "available_qty": 15, "requested_qty": 2, "ok": true }
  ]
}

// Response 200 (with unavailable items — not a 4xx, caller decides what to do)
{
  "available": false,
  "items": [
    { "item_id": "uuid", "available_qty": 0, "requested_qty": 2, "ok": false }
  ]
}
```

---

## Contract 3 — Order status (M3 owns, M5 calls)

**Owner:** Member 3  
**Called by:** Member 5 (Lifecycle) to advance order state

### `PATCH /api/v1/orders/{order_id}/status`

```jsonc
// Request  (M5 sends this)
{
  "to_state": "PREPARING",        // must be a legal forward transition
  "actor_id": "uuid",             // staff or admin user ID
  "reason": null                  // required only when to_state = "CANCELLED"
}

// Response 200
{
  "order_id": "uuid",
  "previous_state": "CONFIRMED",
  "current_state": "PREPARING",
  "updated_at": "2026-05-09T12:05:00Z"
}

// Response 409 — illegal transition
{
  "success": false,
  "error": {
    "code": "INVALID_STATE_TRANSITION",
    "message": "Cannot move from PREPARING to PLACED.",
    "details": { "from": "PREPARING", "to": "PLACED" }
  }
}
```

```python
# backend/order/routes.py  (Member 3)
LEGAL_TRANSITIONS = {
    "PLACED": ["PAYMENT_PENDING", "CANCELLED"],
    "PAYMENT_PENDING": ["CONFIRMED", "PAYMENT_FAILED", "CANCELLED"],
    "PAYMENT_FAILED": ["PAYMENT_PENDING"],
    "CONFIRMED": ["PREPARING", "CANCELLED"],
    "PREPARING": ["READY", "CANCELLED"],
    "READY": ["COLLECTED"],
    "COLLECTED": ["COMPLETED"],
}

@router.patch("/{order_id}/status")
@require_auth("staff", "admin")
async def update_order_status(order_id: str, body: StatusUpdateRequest):
    order = await get_order(order_id)
    if body.to_state not in LEGAL_TRANSITIONS.get(order.status, []):
        return err("INVALID_STATE_TRANSITION",
                   f"Cannot move from {order.status} to {body.to_state}.",
                   {"from": order.status, "to": body.to_state}, status=409)
    updated = await transition_order(order_id, body.to_state, body.actor_id, body.reason)
    return ok(updated.to_dict())
```

```jsx
// frontend/lifecycle/StaffDashboard.jsx  (Member 5)
async function advanceOrder(orderId, toState, actorId) {
  // MOCK — replace when M3 merges
  // return { order_id: orderId, current_state: toState };
  return await apiFetch(`/orders/${orderId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ to_state: toState, actor_id: actorId }),
  });
}
```

### `POST /api/v1/orders/{order_id}/cancel`

```jsonc
// Request  (M5 sends this)
{
  "reason_code": "CUSTOMER_REQUEST",  // CUSTOMER_REQUEST | OUT_OF_STOCK | STAFF_ERROR | SYSTEM_ERROR | SUSPICIOUS
  "actor_id": "uuid",
  "actor_role": "student"             // "student" | "staff" | "admin"
}

// Response 200
{
  "cancelled": true,
  "order_id": "uuid",
  "refund_triggered": true,
  "refund_method": "ORIGINAL_PAYMENT"
}

// Response 409 — cannot cancel
{
  "success": false,
  "error": {
    "code": "ORDER_NOT_CANCELLABLE",
    "message": "Order cannot be cancelled after preparation has started.",
    "details": { "current_state": "PREPARING", "actor_role": "student" }
  }
}
```

---

## Contract 4 — Batch cancel (M4 calls M3 — internal scheduled job)

**Owner:** Member 3 (endpoint) · Member 4 (caller — scheduled job)  
**Trigger:** M4's scheduled job every 60 seconds — cancels orders stuck in `PAYMENT_PENDING` > 10 minutes

### `POST /api/v1/internal/orders/batch-cancel`

> **Internal only** — not exposed to the frontend. Protected by a shared internal API key (`X-Internal-Key` header), not JWT.

```jsonc
// Request  (M4 scheduled job sends this)
{
  "order_ids": ["uuid", "uuid"],
  "reason_code": "SYSTEM_ERROR"
}

// Response 200
{
  "cancelled": ["uuid", "uuid"],
  "failed": []
}
```

```python
# backend/stock/jobs.py  (Member 4)
import httpx, os

INTERNAL_KEY = os.environ["INTERNAL_API_KEY"]

async def cancel_stale_payment_orders():
    stale = await get_orders_stuck_in_payment_pending(older_than_minutes=10)
    if not stale:
        return
    async with httpx.AsyncClient() as client:
        await client.post(
            "http://order-service/api/v1/internal/orders/batch-cancel",
            json={"order_ids": [o.id for o in stale], "reason_code": "SYSTEM_ERROR"},
            headers={"X-Internal-Key": INTERNAL_KEY}
        )
```

---

## Contract 5 — User info (M1 owns, M5 calls)

**Owner:** Member 1  
**Called by:** Member 5 for report data and feedback moderation

### `GET /api/v1/users/{user_id}` (admin/staff only)

```jsonc
// Response 200
{
  "id": "uuid",
  "email": "ahmed@university.edu",
  "display_name": "Ahmed",
  "role": "student",
  "status": "active",
  "created_at": "2025-09-01T08:00:00Z"
}
```

---

## Contract 6 — Menu item details (M2 owns, M3/M4/M5 call)

**Owner:** Member 2  
**Called by:** M3 (display in order confirmation), M4 (stock reconciliation), M5 (reports)

### `GET /api/v1/menu/items/{item_id}`

```jsonc
// Response 200
{
  "id": "uuid",
  "name": "Koshary",
  "category": "meals",
  "price": 35.00,
  "stock_qty": 42,
  "max_order_qty": 10,
  "active": true,
  "image_url": "/media/koshary.jpg",
  "average_rating": 4.3
}
```

### `GET /api/v1/menu/items?category=meals&search=kosh&page=1&limit=20`

```jsonc
// Response 200
{
  "items": [ /* array of item objects (same shape as above) */ ],
  "total": 45,
  "page": 1,
  "limit": 20
}
```

---

## Contract 7 — Rating update (M5 owns, M2 reads)

**Owner:** Member 5 (writes ratings)  
**Read by:** Member 2 (displays average on menu page)

> Member 2 does **not** call M5's endpoint directly. M5 writes ratings to the DB; M2 reads `average_rating` from the `menu_items` table, which M5's rating job updates on a 5-minute cache. No HTTP call needed between slices — DB is the shared source of truth here.

```python
# backend/lifecycle/jobs.py  (Member 5)  — updates menu_items.average_rating
async def refresh_item_ratings():
    await db.execute("""
        UPDATE menu_items
        SET average_rating = (
            SELECT ROUND(AVG(stars)::numeric, 1)
            FROM ratings r
            JOIN orders o ON r.order_id = o.id
            WHERE o.items @> jsonb_build_array(jsonb_build_object('item_id', menu_items.id::text))
            AND r.hidden = false
        )
    """)
```

---

## Shared data models

These TypeScript-style types are the contract for what travels over the wire. Python Pydantic models and React components must match these exactly.

```ts
// shared/types.ts  — commit this to the repo root on Day 1

type Role      = "student" | "staff" | "admin";
type OrderStatus =
  | "DRAFT" | "PLACED" | "PAYMENT_PENDING"
  | "CONFIRMED" | "PREPARING" | "READY"
  | "COLLECTED" | "COMPLETED"
  | "CANCELLED" | "PAYMENT_FAILED";
type PaymentMethod = "ONLINE" | "CASH" | "WALLET" | "MEAL_PLAN";
type ReasonCode = "CUSTOMER_REQUEST" | "OUT_OF_STOCK" | "STAFF_ERROR" | "SYSTEM_ERROR" | "SUSPICIOUS";

interface User {
  id: string;
  email: string;
  display_name: string;
  role: Role;
  status: "active" | "suspended";
  wallet_balance: number;
  meal_plan_balance: number;
}

interface MenuItem {
  id: string;
  name: string;
  category: string;
  price: number;
  stock_qty: number;
  max_order_qty: number;
  active: boolean;
  image_url: string | null;
  average_rating: number | null;
}

interface OrderItem {
  item_id: string;
  name: string;
  quantity: number;
  unit_price: number;
  subtotal: number;
}

interface Order {
  id: string;
  user_id: string;
  status: OrderStatus;
  payment_method: PaymentMethod | null;
  items: OrderItem[];
  voucher_code: string | null;
  subtotal: number;
  discount: number;
  total: number;
  idempotency_key: string;
  created_at: string;
  updated_at: string;
}
```

---

## Mocking guide (for blocked members)

When your dependency slice isn't merged yet, use these mock helpers in React:

```js
// frontend/shared/mocks.js

export const MOCKS = {
  // M3 mocks M4's stock lock while M4 is building
  "POST /stock/lock": (body) => ({
    locked: true,
    order_id: body.order_id,
    expires_at: new Date(Date.now() + 600_000).toISOString(),
  }),

  // M5 mocks M3's status update while M3 is building
  "PATCH /orders/:id/status": (body) => ({
    order_id: "mock-order-id",
    previous_state: "CONFIRMED",
    current_state: body.to_state,
    updated_at: new Date().toISOString(),
  }),

  // M2 mocks M1's /auth/me while M1 is building
  "GET /auth/me": () => ({
    id: "mock-user-id",
    email: "test@university.edu",
    role: "student",
    wallet_balance: 200.00,
    meal_plan_balance: 500.00,
  }),
};

// Toggle mocks with an env variable
export const isMock = (path) =>
  import.meta.env.VITE_USE_MOCKS === "true" && MOCKS[path];
```

---

## Environment variables

Each member needs these in their `.env.local` (never commit `.env` files):

```bash
# All members
VITE_API_BASE=http://localhost:8000/api/v1
VITE_USE_MOCKS=true        # set false when dependencies are merged

# Backend (Python / FastAPI)
DATABASE_URL=postgresql://user:pass@localhost:5432/cafeteria
JWT_SECRET=change-me-in-production
JWT_EXPIRE_MINUTES=30
REDIS_URL=redis://localhost:6379
INTERNAL_API_KEY=change-me-in-production
PAYMENT_GATEWAY_KEY=sandbox-key-here
PAYMENT_GATEWAY_WEBHOOK_SECRET=sandbox-webhook-secret
```

---

## Change log

| Version | Date | Changed by | Summary |
|---|---|---|---|
| 1.0 | 2026-05-09 | Member 1 (Lead) | Initial contracts for all 7 cross-slice dependencies |

> **To update:** create a branch `docs/api-contracts-vX.Y`, edit this file, open PR, tag all 5 members. Minimum 2 approvals required before merge.
