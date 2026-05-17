"""
CSE323 Cafeteria System — Member 3: Order & Payment
"""

import os, uuid, threading
from datetime import datetime, timezone, timedelta
from enum import Enum as PyEnum

from flask import Flask, Blueprint, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import text

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
DATABASE_URL            = os.getenv("DATABASE_URL", "postgresql://cafeteria_user:cafeteria_pass@localhost:5432/cafeteria_db")
PAYMENT_TIMEOUT_SECONDS = 600   
STOCK_LOCK_TTL          = 600   
MAX_ITEM_QUANTITY       = 20    
CANCELLATION_WINDOW_MIN = 15    
MAX_CONCURRENT_ORDERS   = 150   
IDEMPOTENCY_WINDOW_SEC  = 60    
MAX_PAYMENT_RETRIES     = 3     

# ─────────────────────────────────────────────────────────────
# APP + DB  (standalone mode)
# ─────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"]        = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"]                     = os.getenv("SECRET_KEY", "dev-secret-key-m3")

db = SQLAlchemy(app)
CORS(app, resources={r"/*": {"origins": "*"}})

# ─────────────────────────────────────────────────────────────
# BLUEPRINTS DEFINITION (Defined early so routes don't crash)
# ─────────────────────────────────────────────────────────────
order_bp   = Blueprint("orders",   __name__)
payment_bp = Blueprint("payments", __name__)

# ─────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────
class OrderStatus(PyEnum):
    PENDING_PAYMENT = "pending_payment"
    CONFIRMED       = "confirmed"
    PREPARING       = "preparing"
    READY           = "ready_for_pickup"
    DELIVERED       = "delivered"
    CANCELLED       = "cancelled"
    PAYMENT_TIMEOUT = "payment_timeout"

class PaymentMethod(PyEnum):
    ONLINE    = "online"
    CASH      = "cash"
    WALLET    = "wallet"
    MEAL_PLAN = "meal_plan"

class PaymentStatus(PyEnum):
    PENDING       = "pending"
    SUCCESS       = "success"
    FAILED        = "failed"
    TIMEOUT       = "timeout"
    REFUNDED      = "refunded"
    INDETERMINATE = "indeterminate"

def gen_uuid():
    return str(uuid.uuid4())

# ─────────────────────────────────────────────────────────────
# MODELS 
# ─────────────────────────────────────────────────────────────
class MenuItem(db.Model):
    __tablename__ = "menu_items"
    id             = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    name           = db.Column(db.String(120), nullable=False)
    description    = db.Column(db.Text)
    price          = db.Column(db.Numeric(10, 2), nullable=False)
    category       = db.Column(db.String(60))
    image_url      = db.Column(db.String(255))
    is_available   = db.Column(db.Boolean, default=True, nullable=False)
    stock_count    = db.Column(db.Integer, default=0, nullable=False)
    reserved_count = db.Column(db.Integer, default=0, nullable=False)  
    created_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at     = db.Column(db.DateTime, onupdate=lambda: datetime.now(timezone.utc))

    @property
    def available_stock(self):
        return self.stock_count - self.reserved_count

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "price": float(self.price), "category": self.category,
            "image_url": self.image_url, "is_available": self.is_available,
            "stock_count": self.stock_count, "available_stock": self.available_stock,
        }

class Cart(db.Model):
    __tablename__ = "carts"
    id         = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    user_id    = db.Column(db.String(36), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, onupdate=lambda: datetime.now(timezone.utc))
    items      = db.relationship("CartItem", backref="cart", cascade="all, delete-orphan", lazy=True)

    def to_dict(self):
        items    = [i.to_dict() for i in self.items]
        subtotal = sum(i["subtotal"] for i in items)
        return {"id": self.id, "user_id": self.user_id, "items": items, "subtotal": subtotal}

class CartItem(db.Model):
    __tablename__ = "cart_items"
    id           = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    cart_id      = db.Column(db.String(36), db.ForeignKey("carts.id"), nullable=False)
    menu_item_id = db.Column(db.String(36), db.ForeignKey("menu_items.id"), nullable=False)
    quantity     = db.Column(db.Integer, nullable=False, default=1)
    menu_item    = db.relationship("MenuItem", lazy=True)

    def to_dict(self):
        m = self.menu_item
        return {
            "id": self.id, "menu_item_id": self.menu_item_id,
            "name": m.name if m else "", "price": float(m.price) if m else 0,
            "quantity": self.quantity,
            "subtotal": float(m.price) * self.quantity if m else 0,
            "is_available": m.is_available if m else False,
        }

class Voucher(db.Model):
    __tablename__  = "vouchers"
    id             = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    code           = db.Column(db.String(50), unique=True, nullable=False, index=True)
    discount_type  = db.Column(db.String(20))
    discount_value = db.Column(db.Numeric(10, 2), default=0)
    min_order      = db.Column(db.Numeric(10, 2), default=0)
    max_uses       = db.Column(db.Integer, default=1)
    used_count     = db.Column(db.Integer, default=0)
    expires_at     = db.Column(db.DateTime)
    is_active      = db.Column(db.Boolean, default=True)

    def is_valid(self):
        if not self.is_active:               return False, "Voucher is inactive"
        if self.used_count >= self.max_uses: return False, "Voucher already used"
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at.replace(tzinfo=timezone.utc):
            return False, "This voucher has expired"
        return True, "OK"

    def compute_discount(self, subtotal):
        if self.discount_type == "flat":    return min(float(self.discount_value), subtotal)
        if self.discount_type == "percent": return round(subtotal * float(self.discount_value) / 100, 2)
        return 0

    def to_dict(self):
        return {
            "id": self.id, "code": self.code,
            "discount_type": self.discount_type,
            "discount_value": float(self.discount_value),
            "min_order": float(self.min_order),
        }

class Order(db.Model):
    __tablename__   = "orders"
    id              = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    idempotency_key = db.Column(db.String(100), unique=True, nullable=False, index=True) 
    user_id         = db.Column(db.String(36), nullable=False, index=True)
    status          = db.Column(db.Enum(OrderStatus), default=OrderStatus.PENDING_PAYMENT, nullable=False)
    payment_method  = db.Column(db.Enum(PaymentMethod))
    subtotal        = db.Column(db.Numeric(10, 2), nullable=False)
    discount        = db.Column(db.Numeric(10, 2), default=0)
    total           = db.Column(db.Numeric(10, 2), nullable=False)
    voucher_id      = db.Column(db.String(36), db.ForeignKey("vouchers.id"))
    voucher_code    = db.Column(db.String(50))
    notes           = db.Column(db.Text)
    retry_count     = db.Column(db.Integer, default=0)  
    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = db.Column(db.DateTime, onupdate=lambda: datetime.now(timezone.utc))
    confirmed_at    = db.Column(db.DateTime)
    cancelled_at    = db.Column(db.DateTime)
    items    = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan", lazy=True)
    payments = db.relationship("Payment", backref="order_rel", lazy=True)
    voucher  = db.relationship("Voucher", lazy=True)

    def to_dict(self, include_items=True):
        data = {
            "id": self.id, "user_id": self.user_id,
            "status": self.status.value,
            "payment_method": self.payment_method.value if self.payment_method else None,
            "subtotal": float(self.subtotal), "discount": float(self.discount),
            "total": float(self.total), "voucher_code": self.voucher_code,
            "notes": self.notes, "retry_count": self.retry_count or 0,
            "created_at":   self.created_at.isoformat()  if self.created_at  else None,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
        }
        if include_items:
            data["items"] = [i.to_dict() for i in self.items]
        return data

class OrderItem(db.Model):
    __tablename__ = "order_items"
    id           = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    order_id     = db.Column(db.String(36), db.ForeignKey("orders.id"), nullable=False)
    menu_item_id = db.Column(db.String(36), db.ForeignKey("menu_items.id"), nullable=False)
    name         = db.Column(db.String(120), nullable=False)
    unit_price   = db.Column(db.Numeric(10, 2), nullable=False)
    quantity     = db.Column(db.Integer, nullable=False)
    subtotal     = db.Column(db.Numeric(10, 2), nullable=False)
    menu_item    = db.relationship("MenuItem", lazy=True)

    def to_dict(self):
        return {
            "id": self.id, "menu_item_id": self.menu_item_id,
            "name": self.name, "unit_price": float(self.unit_price),
            "quantity": self.quantity, "subtotal": float(self.subtotal),
        }

class Payment(db.Model):
    __tablename__    = "payments"
    id               = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    order_id         = db.Column(db.String(36), db.ForeignKey("orders.id"), nullable=False, index=True)
    method           = db.Column(db.Enum(PaymentMethod), nullable=False)
    status           = db.Column(db.Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    amount           = db.Column(db.Numeric(10, 2), nullable=False)
    transaction_id   = db.Column(db.String(120), unique=True)
    gateway_response = db.Column(db.JSON)
    failure_reason   = db.Column(db.String(255))
    refund_amount    = db.Column(db.Numeric(10, 2))
    refund_ref       = db.Column(db.String(120))
    created_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at       = db.Column(db.DateTime, onupdate=lambda: datetime.now(timezone.utc))
    timeout_at       = db.Column(db.DateTime) 

    def to_dict(self):
        return {
            "id": self.id, "order_id": self.order_id,
            "method": self.method.value, "status": self.status.value,
            "amount": float(self.amount),
            "transaction_id": self.transaction_id,
            "failure_reason": self.failure_reason,
            "refund_amount": float(self.refund_amount) if self.refund_amount else None,
            "refund_ref": self.refund_ref,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "timeout_at": self.timeout_at.isoformat() if self.timeout_at else None,
        }

# ─────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────
def _is_prepaid(order):
    return order.payment_method in [PaymentMethod.ONLINE, PaymentMethod.WALLET, PaymentMethod.MEAL_PLAN]

def _release_stock(order):
    for oi in order.items:
        item = db.session.get(MenuItem, oi.menu_item_id)
        if item:
            item.reserved_count = max(0, item.reserved_count - oi.quantity)

def _deduct_stock(order):
    for oi in order.items:
        item = db.session.get(MenuItem, oi.menu_item_id)
        if item:
            item.stock_count    = max(0, item.stock_count    - oi.quantity)
            item.reserved_count = max(0, item.reserved_count - oi.quantity)

def _initiate_refund(order, full=True, percent=1.0):
    amount  = float(order.total) if full else round(float(order.total) * percent, 2)
    payment = Payment.query.filter_by(order_id=order.id).order_by(Payment.created_at.desc()).first()
    if payment:
        payment.refund_amount = amount
        payment.refund_ref    = f"REF-{uuid.uuid4().hex[:10].upper()}"
        return {"refund_amount": amount, "refund_ref": payment.refund_ref, "eta_days": "3-5 business days"}
    return {"refund_amount": amount, "message": "Refund will be processed manually"}

def _handle_timeout(payment, order, commit=True):
    payment.status = PaymentStatus.TIMEOUT
    if order and order.status == OrderStatus.PENDING_PAYMENT:
        order.status = OrderStatus.PAYMENT_TIMEOUT
        _release_stock(order)  
    if commit:
        db.session.commit()
    return jsonify({
        "success": False,
        "message": "Payment session has timed out. Your cart has been preserved.",
        "code": "PAYMENT_TIMEOUT",
        "payment": payment.to_dict()
    }), 408

def _friendly_failure(reason):
    return {
        "insufficient_funds": "Payment declined: Insufficient funds",
        "card_expired":       "Payment declined: Card expired",
        "gateway_error":      "Payment service unavailable. Please try again",
    }.get(reason, f"Payment declined: {reason}")


# ─────────────────────────────────────────────────────────────
# BACKGROUND JOB: Stock Lock TTL Release 
# ─────────────────────────────────────────────────────────────
def _stock_lock_cleanup_job():
    import time
    while True:
        time.sleep(60)
        try:
            with app.app_context():
                now     = datetime.now(timezone.utc)
                cutoff  = now - timedelta(seconds=STOCK_LOCK_TTL)
                expired = Payment.query.filter(
                    Payment.status == PaymentStatus.PENDING,
                    Payment.created_at <= cutoff
                ).all()
                for p in expired:
                    order = db.session.get(Order, p.order_id)
                    if order and order.status == OrderStatus.PENDING_PAYMENT:
                        _handle_timeout(p, order, commit=False)
                if expired:
                    db.session.commit()
        except Exception as e:
            pass

_cleanup_thread = threading.Thread(target=_stock_lock_cleanup_job, daemon=True)
_cleanup_thread.start()


# ════════════════════════════════════════════════════════════
# MOCK / BOOTSTRAP ROUTES FOR STANDALONE TESTING
# ════════════════════════════════════════════════════════════
@app.route("/", methods=["GET"])
@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "message": "Backend is online"}), 200

@app.route("/api/menu", methods=["GET"])
@app.route("/api/menu-items", methods=["GET"])
def get_menu():
    # FIXED: Returns a pure array so React's map() does not crash
    items = MenuItem.query.all()
    if not items:
        sample_items = [
            MenuItem(name="Classic Cheeseburger", description="Juicy beef patty with melted cheese", price=120.00, stock_count=50),
            MenuItem(name="Club Sandwich", description="Toasted chicken sandwich with fries", price=85.00, stock_count=30),
            MenuItem(name="Iced Latte", description="Freshly brewed espresso with cold milk", price=60.00, stock_count=100)
        ]
        db.session.add_all(sample_items)
        db.session.commit()
        items = MenuItem.query.all()
    return jsonify([i.to_dict() for i in items])

@app.route("/api/carts/<user_id>", methods=["GET"])
@app.route("/api/cart/<user_id>", methods=["GET"])
def get_mock_cart(user_id):
    cart = Cart.query.filter_by(user_id=user_id).first()
    if not cart:
        cart = Cart(user_id=user_id)
        db.session.add(cart)
        db.session.commit()
    return jsonify({"success": True, "cart": cart.to_dict()})


# ════════════════════════════════════════════════════════════
# ORDER ROUTES
# ════════════════════════════════════════════════════════════
@order_bp.route("/api/orders", methods=["POST"])
def place_order():
    d               = request.get_json() or {}
    user_id         = d.get("user_id") or "guest-user"
    idempotency_key = d.get("idempotency_key") or request.headers.get("X-Idempotency-Key") or f"AUTO-{uuid.uuid4().hex}"
    voucher_code    = (d.get("voucher_code") or "").strip().upper() or None
    notes           = d.get("notes", "")

    existing = Order.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        age = (datetime.now(timezone.utc) - existing.created_at.replace(tzinfo=timezone.utc)).total_seconds()
        if age <= IDEMPOTENCY_WINDOW_SEC:
            return jsonify({"success": True, "order": existing.to_dict(), "duplicate": True}), 200

    active = Order.query.filter(Order.status.in_([
        OrderStatus.PENDING_PAYMENT, OrderStatus.CONFIRMED, OrderStatus.PREPARING
    ])).count()
    if active >= MAX_CONCURRENT_ORDERS:
        resp = jsonify({"success": False, "error": "Service temporarily busy. Please try again shortly.", "code": "SYSTEM_OVERLOADED"})
        resp.headers["Retry-After"] = "30"
        return resp, 503

    # FIXED: Accepts items sent directly from React state, ignoring empty database carts
    cart_items_data = d.get("items") or []
    if not cart_items_data:
        cart = Cart.query.filter_by(user_id=user_id).first()
        if cart and cart.items:
            cart_items_data = [{"menu_item_id": i.menu_item_id, "quantity": i.quantity} for i in cart.items]
            CartItem.query.filter_by(cart_id=cart.id).delete()

    if not cart_items_data:
        return jsonify({"success": False, "error": "Cart is empty"}), 400

    try:
        subtotal, order_items_data = 0.0, []

        for ci in cart_items_data:
            item_id = ci.get("menu_item_id") or ci.get("id")
            quantity = ci.get("quantity", 1)
            
            try:
                item = db.session.get(MenuItem, item_id, with_for_update={"nowait": True})
            except Exception:
                db.session.rollback()
                return jsonify({"success": False, "error": "Item temporarily locked by another order. Please try again."}), 409

            if not item or not item.is_available:
                return jsonify({"success": False, "error": f"Item {item_id} unavailable"}), 409

            if quantity > MAX_ITEM_QUANTITY:
                return jsonify({"success": False, "error": f"Maximum {MAX_ITEM_QUANTITY} units per item"}), 400

            if item.available_stock < quantity:
                db.session.rollback()
                return jsonify({"success": False, "error": f"'{item.name}' short on stock."}), 409

            item.reserved_count += quantity  
            line = float(item.price) * quantity
            subtotal += line
            order_items_data.append({
                "menu_item_id": item.id, "name": item.name,
                "unit_price": float(item.price), "quantity": quantity, "subtotal": line,
            })

        discount, voucher_id = 0.0, None
        if voucher_code:
            v = Voucher.query.filter_by(code=voucher_code).first()
            if v:
                valid, _ = v.is_valid()
                if valid and subtotal >= float(v.min_order):
                    discount = v.compute_discount(subtotal)
                    voucher_id = v.id
                    v.used_count += 1

        order = Order(
            idempotency_key=idempotency_key, user_id=user_id,
            status=OrderStatus.PENDING_PAYMENT,
            subtotal=subtotal, discount=discount,
            total=round(subtotal - discount, 2),
            voucher_id=voucher_id,
            voucher_code=voucher_code if voucher_id else None,
            notes=notes, retry_count=0,
        )
        db.session.add(order)
        db.session.flush()

        for od in order_items_data:
            db.session.add(OrderItem(
                order_id=order.id, menu_item_id=od["menu_item_id"],
                name=od["name"], unit_price=od["unit_price"],
                quantity=od["quantity"], subtotal=od["subtotal"],
            ))
            
        db.session.commit()
        return jsonify({"success": True, "order": order.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": "Order processing failed", "detail": str(e)}), 500


@order_bp.route("/api/orders/<order_id>", methods=["GET"])
def get_order(order_id):
    order = db.session.get(Order, order_id)
    if not order: return jsonify({"success": False, "error": "Order not found"}), 404
    data = order.to_dict()
    data["payments"] = [p.to_dict() for p in order.payments]
    return jsonify({"success": True, "order": data})

@order_bp.route("/api/orders/user/<user_id>", methods=["GET"])
def list_orders(user_id):
    orders = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).all()
    return jsonify({"success": True, "orders": [o.to_dict(include_items=False) for o in orders]})

@order_bp.route("/api/orders/<order_id>/cancel", methods=["PUT"])
def cancel_order(order_id):
    order = db.session.get(Order, order_id)
    if not order: return jsonify({"success": False, "error": "Order not found"}), 404
    now = datetime.now(timezone.utc)

    if order.status == OrderStatus.PENDING_PAYMENT:
        order.status = OrderStatus.CANCELLED
        order.cancelled_at = now
        _release_stock(order)
        db.session.commit()
        return jsonify({"success": True, "message": "Order cancelled successfully", "refund": None})

    if order.status == OrderStatus.CONFIRMED:
        confirmed_at = order.confirmed_at.replace(tzinfo=timezone.utc) if order.confirmed_at else now
        if now <= confirmed_at + timedelta(minutes=CANCELLATION_WINDOW_MIN):
            order.status = OrderStatus.CANCELLED
            order.cancelled_at = now
            _release_stock(order)
            refund = _initiate_refund(order, full=True) if _is_prepaid(order) else None
            db.session.commit()
            return jsonify({"success": True, "message": "Order cancelled with full refund", "refund": refund})
        elif _is_prepaid(order):
            return jsonify({"success": False, "code": "CANCELLATION_WINDOW_PASSED", "message": "Window passed. Partial refund may apply.", "partial_refund_amount": round(float(order.total) * 0.5, 2), "requires_confirmation": True})
        
    return jsonify({"success": False, "error": "Order cannot be cancelled at this stage"}), 409

@order_bp.route("/api/vouchers/validate", methods=["POST"])
def validate_voucher():
    d = request.get_json() or {}
    voucher = Voucher.query.filter_by(code=(d.get("code") or "").strip().upper()).first()
    if not voucher: return jsonify({"success": False, "error": "Invalid voucher code"}), 400
    subtotal = float(d.get("subtotal", 0))
    valid, msg = voucher.is_valid()
    if not valid: return jsonify({"success": False, "error": msg}), 400
    if subtotal < float(voucher.min_order): return jsonify({"success": False, "error": f"Minimum order of {voucher.min_order} required"}), 400
    discount = voucher.compute_discount(subtotal)
    return jsonify({"success": True, "voucher": voucher.to_dict(), "discount": discount, "new_total": round(subtotal - discount, 2)})

# ════════════════════════════════════════════════════════════
# PAYMENT ROUTES
# ════════════════════════════════════════════════════════════
@payment_bp.route("/api/payments/process", methods=["POST"])
@payment_bp.route("/api/payments/initiate", methods=["POST"])
def initiate_payment():
    d        = request.get_json() or {}
    order_id = d.get("order_id")
    
    # FIXED: Soft string matching for payment methods so it doesn't crash on uppercase/variations
    method_str = str(d.get("payment_method", "cash")).lower().strip()
    if "card" in method_str: pm = PaymentMethod.ONLINE
    elif "plan" in method_str: pm = PaymentMethod.MEAL_PLAN
    elif "wallet" in method_str: pm = PaymentMethod.WALLET
    else: pm = PaymentMethod.CASH

    order = db.session.get(Order, order_id)
    if not order: return jsonify({"success": False, "error": "Order not found"}), 404
    if order.status != OrderStatus.PENDING_PAYMENT: return jsonify({"success": False, "error": "Order is not awaiting payment"}), 409
    
    if pm == PaymentMethod.MEAL_PLAN:
        if float(d.get("meal_plan_balance", 0)) < float(order.total):
            return jsonify({"success": False, "error": "INSUFFICIENT_MEAL_PLAN_BALANCE"}), 422

    order.payment_method = pm
    timeout_at = datetime.now(timezone.utc) + timedelta(seconds=PAYMENT_TIMEOUT_SECONDS)
    payment = Payment(order_id=order.id, method=pm, status=PaymentStatus.PENDING, amount=order.total, timeout_at=timeout_at)
    db.session.add(payment)
    db.session.commit()

    if pm in [PaymentMethod.CASH, PaymentMethod.WALLET, PaymentMethod.MEAL_PLAN]:
        payment.status         = PaymentStatus.SUCCESS
        payment.transaction_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"
        order.status           = OrderStatus.CONFIRMED
        order.confirmed_at     = datetime.now(timezone.utc)
        _deduct_stock(order)
        db.session.commit()
        return jsonify({"success": True, "message": "Payment confirmed successfully.", "order_status": order.status.value, "payment": payment.to_dict()})

    gateway_url = f"https://payment-gateway.example.com/pay?ref={payment.id}&amount={order.total}"
    return jsonify({"success": True, "payment_id": payment.id, "gateway_url": gateway_url, "timeout_at": timeout_at.isoformat(), "method": pm.value})

# ─────────────────────────────────────────────────────────────
# STARTUP SEQUENCE
# ─────────────────────────────────────────────────────────────
app.register_blueprint(order_bp)
app.register_blueprint(payment_bp)

with app.app_context():
    # FIXED: Forcefully wipe old tables to avoid psycopg2 DependentObjectsStillExist crashes
    db.session.execute(text("DROP TABLE IF EXISTS payments CASCADE;"))
    db.session.execute(text("DROP TABLE IF EXISTS order_items CASCADE;"))
    db.session.execute(text("DROP TABLE IF EXISTS orders CASCADE;"))
    db.session.execute(text("DROP TABLE IF EXISTS cart_items CASCADE;"))
    db.session.execute(text("DROP TABLE IF EXISTS carts CASCADE;"))
    db.session.execute(text("DROP TABLE IF EXISTS vouchers CASCADE;"))
    db.session.execute(text("DROP TABLE IF EXISTS menu_items CASCADE;"))
    db.session.commit()
    
    # Create fresh tables
    db.create_all()

if __name__ == "__main__":
    print("\n" + "="*65)
    print("✅✅✅ IF YOU SEE THIS, THE NEW PATCHED CODE IS RUNNING! ✅✅✅")
    print("="*65 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=True)