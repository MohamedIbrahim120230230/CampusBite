"""
CSE323 Cafeteria System — Member 3: Order & Payment (REWRITTEN FOR INTEGRATION)
"""

import os
import uuid
import threading
import time
import psycopg2
import psycopg2.extras
import json
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify

# ─────────────────────────────────────────────────────────────
# CONFIG & CONSTANTS
# ─────────────────────────────────────────────────────────────
PAYMENT_TIMEOUT_SECONDS = 600   
CANCELLATION_WINDOW_MIN = 15    
MAX_CONCURRENT_ORDERS   = 150   
IDEMPOTENCY_WINDOW_SEC  = 60    
MAX_ITEM_QUANTITY       = 20    

order_bp   = Blueprint("orders",   __name__)
payment_bp = Blueprint("payments", __name__)

def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "cafeteria"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        port=os.getenv("DB_PORT", "5432")
    )

def gen_uuid():
    return str(uuid.uuid4())

# ─────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────
def _is_prepaid(method):
    return method in ["online", "wallet", "meal_plan"]

def _release_stock(cur, order_id):
    """Restores stock for cancelled/timed-out orders."""
    cur.execute("SELECT menu_item_id, quantity FROM order_items WHERE order_id = %s", (order_id,))
    for item in cur.fetchall():
        cur.execute("UPDATE menu_items SET stock_qty = stock_qty + %s WHERE id = %s", 
                    (item["quantity"], item["menu_item_id"]))

def _initiate_refund(cur, order_id, total, full=True, percent=1.0):
    amount = float(total) if full else round(float(total) * percent, 2)
    cur.execute("SELECT id FROM payments WHERE order_id = %s ORDER BY created_at DESC LIMIT 1", (order_id,))
    payment = cur.fetchone()
    
    if payment:
        refund_ref = f"REF-{uuid.uuid4().hex[:10].upper()}"
        cur.execute("UPDATE payments SET refund_amount = %s, refund_ref = %s WHERE id = %s", 
                    (amount, refund_ref, payment["id"]))
        return {"refund_amount": amount, "refund_ref": refund_ref, "eta_days": "3-5 business days"}
    return {"refund_amount": amount, "message": "Refund will be processed manually"}

# ════════════════════════════════════════════════════════════
# ORDER ROUTES
# ════════════════════════════════════════════════════════════
@order_bp.route("/api/orders", methods=["POST"])
def place_order():
    d = request.get_json() or {}
    user_id = d.get("user_id", "guest-user")
    idempotency_key = d.get("idempotency_key") or request.headers.get("X-Idempotency-Key") or f"AUTO-{uuid.uuid4().hex}"
    voucher_code = (d.get("voucher_code") or "").strip().upper() or None
    notes = d.get("notes", "")

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Check idempotency
        cur.execute("SELECT * FROM orders WHERE idempotency_key = %s", (idempotency_key,))
        existing = cur.fetchone()
        if existing:
            age = (datetime.now(timezone.utc) - existing["created_at"].replace(tzinfo=timezone.utc)).total_seconds()
            if age <= IDEMPOTENCY_WINDOW_SEC:
                return jsonify({"success": True, "order": existing, "duplicate": True}), 200

        # Enforce concurrency limits
        cur.execute("SELECT COUNT(*) as count FROM orders WHERE status IN ('pending_payment', 'confirmed', 'preparing')")
        if cur.fetchone()["count"] >= MAX_CONCURRENT_ORDERS:
            return jsonify({"success": False, "error": "Service temporarily busy.", "code": "SYSTEM_OVERLOADED"}), 503

        # Resolve Cart Items (Fallback to Member 2's cart_sessions table)
        cart_items_data = d.get("items", [])
        if not cart_items_data:
            try:
                cur.execute("SELECT items FROM cart_sessions WHERE user_id = %s::uuid", (user_id,))
                cart_row = cur.fetchone()
                if cart_row and cart_row["items"]:
                    cart_items_data = cart_row["items"] if isinstance(cart_row["items"], list) else json.loads(cart_row["items"])
            except psycopg2.errors.InvalidTextRepresentation:
                pass # user_id is 'guest-user', ignore uuid parse error

        if not cart_items_data:
            return jsonify({"success": False, "error": "Cart is empty"}), 400

        subtotal = 0.0
        order_items_insert = []

        # Lock rows and check stock for Member 2's menu_items
        for ci in cart_items_data:
            # Handle frontend structure differences
            item_id = ci.get("menu_item_id") or ci.get("id") or ci.get("item_id")
            quantity = ci.get("qty") or ci.get("quantity", 1)

            if quantity > MAX_ITEM_QUANTITY:
                return jsonify({"success": False, "error": f"Max {MAX_ITEM_QUANTITY} units per item"}), 400

            cur.execute("SELECT id, name, price, stock_qty, active FROM menu_items WHERE id = %s FOR UPDATE NOWAIT", (item_id,))
            item = cur.fetchone()

            if not item or not item["active"]:
                conn.rollback()
                return jsonify({"success": False, "error": f"Item unavailable"}), 409
            
            if item["stock_qty"] < quantity:
                conn.rollback()
                return jsonify({"success": False, "error": f"'{item['name']}' is short on stock."}), 409

            line_total = float(item["price"]) * quantity
            subtotal += line_total
            order_items_insert.append({
                "menu_item_id": item["id"], "name": item["name"], 
                "unit_price": float(item["price"]), "quantity": quantity, "subtotal": line_total
            })

            # Instantly deduct stock
            cur.execute("UPDATE menu_items SET stock_qty = stock_qty - %s WHERE id = %s", (quantity, item_id))

        # Voucher logic
        discount, voucher_id = 0.0, None
        if voucher_code:
            cur.execute("SELECT * FROM vouchers WHERE code = %s AND is_active = TRUE", (voucher_code,))
            v = cur.fetchone()
            if v and v["used_count"] < v["max_uses"]:
                # Expiry check
                is_expired = False
                if v["expires_at"]:
                    # Account for offset-naive vs aware
                    expires_aware = v["expires_at"] if v["expires_at"].tzinfo else v["expires_at"].replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) > expires_aware:
                        is_expired = True
                
                if not is_expired and subtotal >= float(v["min_order"]):
                    if v["discount_type"] == "flat": discount = min(float(v["discount_value"]), subtotal)
                    elif v["discount_type"] == "percent": discount = round(subtotal * float(v["discount_value"]) / 100, 2)
                    voucher_id = v["id"]
                    cur.execute("UPDATE vouchers SET used_count = used_count + 1 WHERE id = %s", (voucher_id,))

        total = round(subtotal - discount, 2)
        order_id = gen_uuid()

        # Insert Order
        cur.execute("""
            INSERT INTO orders (id, idempotency_key, user_id, status, subtotal, discount, total, voucher_id, voucher_code, notes, created_at)
            VALUES (%s, %s, %s, 'pending_payment', %s, %s, %s, %s, %s, %s, NOW())
        """, (order_id, idempotency_key, user_id, subtotal, discount, total, voucher_id, voucher_code, notes))

        # Insert Order Items
        for oi in order_items_insert:
            cur.execute("""
                INSERT INTO order_items (id, order_id, menu_item_id, name, unit_price, quantity, subtotal)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (gen_uuid(), order_id, oi["menu_item_id"], oi["name"], oi["unit_price"], oi["quantity"], oi["subtotal"]))

        # Clear Cart
        try:
            cur.execute("UPDATE cart_sessions SET items = '[]'::jsonb WHERE user_id = %s::uuid", (user_id,))
        except psycopg2.errors.InvalidTextRepresentation:
            pass 

        conn.commit()
        return jsonify({"success": True, "order_id": order_id, "total": total, "status": "pending_payment"}), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@order_bp.route("/api/orders/<order_id>", methods=["GET"])
def get_order(order_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
    order = cur.fetchone()
    if not order:
        return jsonify({"success": False, "error": "Order not found"}), 404
    
    cur.execute("SELECT * FROM order_items WHERE order_id = %s", (order_id,))
    order["items"] = cur.fetchall()
    
    cur.execute("SELECT * FROM payments WHERE order_id = %s", (order_id,))
    order["payments"] = cur.fetchall()
    
    cur.close()
    conn.close()
    return jsonify({"success": True, "order": order})

@order_bp.route("/api/orders/<order_id>/cancel", methods=["PUT"])
def cancel_order(order_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)

    try:
        cur.execute("SELECT * FROM orders WHERE id = %s FOR UPDATE", (order_id,))
        order = cur.fetchone()
        
        if not order:
            return jsonify({"success": False, "error": "Order not found"}), 404

        if order["status"] == "pending_payment":
            cur.execute("UPDATE orders SET status = 'cancelled', cancelled_at = NOW() WHERE id = %s", (order_id,))
            _release_stock(cur, order_id)
            conn.commit()
            return jsonify({"success": True, "message": "Order cancelled successfully"})

        if order["status"] == "confirmed":
            confirmed_at = order["confirmed_at"] if order["confirmed_at"].tzinfo else order["confirmed_at"].replace(tzinfo=timezone.utc)
            if now <= confirmed_at + timedelta(minutes=CANCELLATION_WINDOW_MIN):
                cur.execute("UPDATE orders SET status = 'cancelled', cancelled_at = NOW() WHERE id = %s", (order_id,))
                _release_stock(cur, order_id)
                refund = _initiate_refund(cur, order_id, order["total"], full=True) if _is_prepaid(order["payment_method"]) else None
                conn.commit()
                return jsonify({"success": True, "message": "Order cancelled with full refund", "refund": refund})
            elif _is_prepaid(order["payment_method"]):
                return jsonify({"success": False, "code": "CANCELLATION_WINDOW_PASSED", "message": "Window passed. Partial refund may apply."})
            
        return jsonify({"success": False, "error": "Order cannot be cancelled at this stage"}), 409

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

# ════════════════════════════════════════════════════════════
# PAYMENT ROUTES
# ════════════════════════════════════════════════════════════
@payment_bp.route("/api/payments/process", methods=["POST"])
@payment_bp.route("/api/payments/initiate", methods=["POST"])
def initiate_payment():
    d = request.get_json() or {}
    order_id = d.get("order_id")
    method_str = str(d.get("payment_method", "cash")).lower().strip()
    
    pm = "cash"
    if "card" in method_str or "online" in method_str: pm = "online"
    elif "plan" in method_str: pm = "meal_plan"
    elif "wallet" in method_str: pm = "wallet"

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("SELECT * FROM orders WHERE id = %s FOR UPDATE", (order_id,))
        order = cur.fetchone()
        
        if not order: return jsonify({"success": False, "error": "Order not found"}), 404
        if order["status"] != "pending_payment": return jsonify({"success": False, "error": "Order is not awaiting payment"}), 409
        
        # Check Member 1's Wallet / Meal Plan limits!
        if pm in ["wallet", "meal_plan"]:
            cur.execute("SELECT wallet_balance, meal_plan_balance FROM users WHERE id = %s::uuid", (order["user_id"],))
            user = cur.fetchone()
            if not user:
                return jsonify({"success": False, "error": "User account not found for balance check"}), 404
                
            if pm == "meal_plan" and float(user["meal_plan_balance"]) < float(order["total"]):
                return jsonify({"success": False, "error": "INSUFFICIENT_MEAL_PLAN_BALANCE"}), 422
            if pm == "wallet" and float(user["wallet_balance"]) < float(order["total"]):
                return jsonify({"success": False, "error": "INSUFFICIENT_WALLET_BALANCE"}), 422

            # Deduct balance
            if pm == "meal_plan":
                cur.execute("UPDATE users SET meal_plan_balance = meal_plan_balance - %s WHERE id = %s::uuid", (order["total"], order["user_id"]))
            elif pm == "wallet":
                cur.execute("UPDATE users SET wallet_balance = wallet_balance - %s WHERE id = %s::uuid", (order["total"], order["user_id"]))

        payment_id = gen_uuid()
        timeout_at = datetime.now(timezone.utc) + timedelta(seconds=PAYMENT_TIMEOUT_SECONDS)

        # External Gateway Link
        if pm == "online":
            cur.execute("""
                INSERT INTO payments (id, order_id, method, status, amount, timeout_at, created_at)
                VALUES (%s, %s, %s, 'pending', %s, %s, NOW())
            """, (payment_id, order_id, pm, order["total"], timeout_at))
            cur.execute("UPDATE orders SET payment_method = %s WHERE id = %s", (pm, order_id))
            conn.commit()
            
            gateway_url = f"https://payment-gateway.example.com/pay?ref={payment_id}&amount={order['total']}"
            return jsonify({"success": True, "payment_id": payment_id, "gateway_url": gateway_url, "timeout_at": timeout_at.isoformat(), "method": pm})

        # Instant clearing (Cash, Wallet, Meal Plan)
        txn_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"
        cur.execute("""
            INSERT INTO payments (id, order_id, method, status, amount, transaction_id, created_at)
            VALUES (%s, %s, %s, 'success', %s, %s, NOW())
        """, (payment_id, order_id, pm, order["total"], txn_id))
        
        cur.execute("UPDATE orders SET status = 'confirmed', confirmed_at = NOW(), payment_method = %s WHERE id = %s", (pm, order_id))
        
        conn.commit()
        return jsonify({"success": True, "message": "Payment confirmed successfully.", "order_status": "confirmed"})

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

# ─────────────────────────────────────────────────────────────
# BACKGROUND JOB: Stock Lock TTL Release (RAW SQL VERSION)
# ─────────────────────────────────────────────────────────────
def _stock_lock_cleanup_job():
    while True:
        time.sleep(60)
        try:
            conn = get_db()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            cur.execute("SELECT id, order_id FROM payments WHERE status = 'pending' AND timeout_at <= NOW()")
            expired_payments = cur.fetchall()
            
            for p in expired_payments:
                cur.execute("UPDATE payments SET status = 'timeout' WHERE id = %s", (p["id"],))
                cur.execute("SELECT status FROM orders WHERE id = %s FOR UPDATE", (p["order_id"],))
                order = cur.fetchone()
                
                if order and order["status"] == "pending_payment":
                    cur.execute("UPDATE orders SET status = 'payment_timeout' WHERE id = %s", (p["order_id"],))
                    _release_stock(cur, p["order_id"])
            
            if expired_payments:
                conn.commit()
                
            cur.close()
            conn.close()
        except Exception as e:
            pass

_cleanup_thread = threading.Thread(target=_stock_lock_cleanup_job, daemon=True)
_cleanup_thread.start()