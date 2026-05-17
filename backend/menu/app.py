from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "cafeteria"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        port=os.getenv("DB_PORT", "5432")
    )

# ── Menu Routes ──────────────────────────────────────────

# FR09 — Browse menu by category
@app.route("/api/menu", methods=["GET"])
def get_menu():
    category = request.args.get("category")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if category:
        cur.execute("SELECT * FROM menu_items WHERE active = TRUE AND category = %s", (category,))
    else:
        cur.execute("SELECT * FROM menu_items WHERE active = TRUE")
    items = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(items)

# FR10 — Search menu
@app.route("/api/menu/search", methods=["GET"])
def search_menu():
    query = request.args.get("q", "")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT * FROM menu_items
        WHERE active = TRUE
        AND to_tsvector('english', name) @@ plainto_tsquery('english', %s)
    """, (query,))
    items = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(items)

# ── Cart Routes ──────────────────────────────────────────

# FR11, FR12 — View cart
@app.route("/api/cart/<string:user_id>", methods=["GET"])
def get_cart(user_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM cart_sessions WHERE user_id = %s::uuid", (user_id,))
    cart = cur.fetchone()
    cur.close()
    conn.close()
    return jsonify(cart or {"user_id": user_id, "items": [], "locked_at": None})

# FR11 — Add item to cart
@app.route("/api/cart/<string:user_id>/add", methods=["POST"])
def add_to_cart(user_id):
    data = request.json
    item_id = data.get("item_id")
    qty = data.get("qty", 1)
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Check item exists, is active, and has stock (FR11)
    cur.execute("SELECT * FROM menu_items WHERE id = %s AND active = TRUE", (item_id,))
    item = cur.fetchone()
    if not item:
        return jsonify({"error": "Item not found or out of stock"}), 404

    # FR19 — max quantity cap
    if qty > item["max_order_qty"]:
        return jsonify({"error": f"Maximum order quantity is {item['max_order_qty']}"}), 400

    # FR11 — check stock
    if item["stock_qty"] < qty:
        return jsonify({"error": "Not enough stock"}), 400

    # Upsert cart
    cur.execute("SELECT * FROM cart_sessions WHERE user_id = %s::uuid", (user_id,))
    cart = cur.fetchone()
    if cart:
        cur.execute("""
            UPDATE cart_sessions SET items = items || %s::jsonb, updated_at = NOW()
            WHERE user_id = %s::uuid
        """, ([{"item_id": item_id, "qty": qty, "price": float(item["price"])}], user_id))
    else:
        cur.execute("""
            INSERT INTO cart_sessions (user_id, items)
            VALUES (%s::uuid, %s::jsonb)
        """, (user_id, [{"item_id": item_id, "qty": qty, "price": float(item["price"])}]))

    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": "Item added to cart"})

# FR13, FR14, FR15, FR16 — Apply voucher
@app.route("/api/cart/<string:user_id>/voucher", methods=["POST"])
def apply_voucher(user_id):
    code = request.json.get("code")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # FR14 — check voucher exists and is valid
    cur.execute("""
        SELECT * FROM vouchers
        WHERE code = %s AND expires_at > NOW()
    """, (code,))
    voucher = cur.fetchone()
    if not voucher:
        return jsonify({"error": "Invalid or expired voucher"}), 400

    # FR14 — check not already used
    if voucher["used_by"] is not None:
        return jsonify({"error": "Voucher already used"}), 400

    # FR15 — check no voucher already applied on cart
    cur.execute("SELECT * FROM cart_sessions WHERE user_id = %s::uuid", (user_id,))
    cart = cur.fetchone()
    if not cart:
        return jsonify({"error": "Cart is empty"}), 400

    # FR15 — check voucher not already applied
    if cart.get("voucher_code"):
        return jsonify({"error": "A voucher has already been applied. Stacking is not allowed"}), 400

    # Calculate total
    items = cart["items"]
    total = sum(i["price"] * i["qty"] for i in items)

    # FR16 — floor at 0
    discount = float(voucher["discount"])
    new_total = max(0, total - discount)

    # Mark voucher as used
    cur.execute("""
        UPDATE vouchers SET used_by = %s::uuid WHERE code = %s
    """, (user_id, code))

    conn.commit()
    cur.close()
    conn.close()
    return jsonify({
        "original_total": total,
        "discount": discount,
        "new_total": new_total,
        "voucher_code": code
    })

# FR17 — Lock cart at checkout
@app.route("/api/cart/<string:user_id>/lock", methods=["POST"])
def lock_cart(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE cart_sessions SET locked_at = NOW()
        WHERE user_id = %s::uuid AND locked_at IS NULL
    """, (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": "Cart locked"})

# ── Admin Routes ─────────────────────────────────────────

# FR18 — Admin CRUD for menu items
@app.route("/api/admin/menu", methods=["POST"])
def create_menu_item():
    data = request.json
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        INSERT INTO menu_items (name, category, price, stock_qty, max_order_qty, active)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING *
    """, (data["name"], data["category"], data["price"],
          data["stock_qty"], data.get("max_order_qty", 10), data.get("active", True)))
    item = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify(item), 201

@app.route("/api/admin/menu/<int:item_id>", methods=["PUT"])
def update_menu_item(item_id):
    data = request.json
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        UPDATE menu_items SET name=%s, category=%s, price=%s,
        stock_qty=%s, max_order_qty=%s, active=%s, updated_at=NOW()
        WHERE id=%s RETURNING *
    """, (data["name"], data["category"], data["price"],
          data["stock_qty"], data["max_order_qty"], data["active"], item_id))
    item = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify(item)

@app.route("/api/admin/menu/<int:item_id>", methods=["DELETE"])
def delete_menu_item(item_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE menu_items SET active = FALSE WHERE id = %s", (item_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": "Item deactivated"})

if __name__ == "__main__":
    app.run(debug=True, port=5001)