"""
T2 Order System — Order Routes

Implement order CRUD, state machine, and payment with idempotency.
Register as a Flask Blueprint named 'order_bp'.

Order state machine:
  pending -> paid -> shipped -> delivered
  pending/paid -> cancelled
"""

from datetime import datetime

from flask import Blueprint, request, jsonify
from models import Product, Order, OrderItem, PaymentRequest, db

order_bp = Blueprint('order_bp', __name__)

# --- State machine whitelist (used by ATU-005, ATU-006) ---

VALID_TRANSITIONS = {
    'pending':  {'pay', 'cancel'},
    'paid':     {'ship', 'cancel'},
    'shipped':  {'deliver'},
    'delivered': set(),
    'cancelled': set(),
}


def validate_transition(order, action):
    """Check whether *action* is allowed for the current order status.

    Returns True if valid, otherwise aborts with 409.
    Does NOT commit; callers manage the transaction.
    """
    allowed = VALID_TRANSITIONS.get(order.status, set())
    if action not in allowed:
        jsonify({"status": "error", "message": "Invalid state transition"})
        return False
    return True


# --- Serialization helpers ---

def serialize_order_item(i):
    """Convert an OrderItem ORM object to a JSON-serializable dict."""
    return {
        "id": i.id,
        "product_id": i.product_id,
        "quantity": i.quantity,
        "unit_price": i.unit_price,
    }


def serialize_order(o, include_items=False):
    """Convert an Order ORM object to a JSON-serializable dict.

    When *include_items* is True the response includes the full list of
    OrderItem records; otherwise items are omitted (avoids N+1 queries).
    """
    data = {
        "id": o.id,
        "user_id": o.user_id,
        "status": o.status,
        "total_amount": o.total_amount,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        "shipped_at": o.shipped_at.isoformat() if o.shipped_at else None,
        "delivered_at": o.delivered_at.isoformat() if o.delivered_at else None,
        "cancelled_at": o.cancelled_at.isoformat() if o.cancelled_at else None,
    }
    if include_items:
        data["items"] = [serialize_order_item(i) for i in o.items]
    return data


# --- Order CRUD routes ---

@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order with pending status.

    Validates that all referenced products exist and have sufficient stock.
    Computes total_amount as the sum of (price * quantity) for all items.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON"}), 400

    # Validate required top-level fields
    user_id = data.get('user_id')
    items = data.get('items')
    if not user_id or not isinstance(items, list) or len(items) == 0:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    # Validate each item and resolve products
    resolved = []
    for item in items:
        quantity = item.get('quantity')
        product_id = item.get('product_id')
        if not isinstance(quantity, int) or quantity < 1:
            return jsonify({"status": "error", "message": "Invalid quantity"}), 400
        product = Product.query.get(product_id)
        if not product:
            return jsonify({"status": "error", "message": f"Product {product_id} not found"}), 400
        if product.stock < quantity:
            return jsonify({"status": "error", "message": "Insufficient stock"}), 400
        resolved.append((product, quantity))

    # Calculate total and persist
    total_amount = sum(p.price * q for p, q in resolved)
    order = Order(user_id=user_id, status='pending', total_amount=total_amount)
    db.session.add(order)
    db.session.flush()  # ensure order.id is available for OrderItem FK

    for product, quantity in resolved:
        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=product.price,
        )
        db.session.add(order_item)

    db.session.commit()
    return jsonify({"status": "ok", "data": serialize_order(order)}), 201


@order_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    """Return the full order details including its items."""
    order = Order.query.get(order_id)
    if not order:
        return jsonify({"status": "error", "message": "Order not found"}), 404
    return jsonify({"status": "ok", "data": serialize_order(order, include_items=True)}), 200


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders, optionally filtered by user_id and/or status.

    Only the query parameters ``user_id`` and ``status`` are recognised;
    all others are silently ignored.
    """
    query = Order.query
    user_id = request.args.get('user_id')
    status = request.args.get('status')
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    if status is not None:
        query = query.filter_by(status=status)
    orders = query.all()
    return jsonify({"status": "ok", "data": [serialize_order(o) for o in orders]}), 200


# --- Payment route (ATU-006) ---

@order_bp.route('/orders/<int:order_id>/pay', methods=['POST'])
def pay_order(order_id):
    """Pay for an order with idempotency support.

    Requires the ``Idempotency-Key`` request header.  If the same key is
    reused for the same order the original result is returned without
    side-effects (idempotent).  On first payment the product stock is
    deducted, a PaymentRequest record is created, and the order status
    transitions to ``paid``.
    """
    # 1. Check Idempotency-Key header
    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify({"status": "error", "message": "Idempotency-Key header is required"}), 400

    # 2. Query order
    order = Order.query.get(order_id)
    if not order:
        return jsonify({"status": "error", "message": "Order not found"}), 404

    # 3. Validate transition (status must be 'pending')
    if not validate_transition(order, 'pay'):
        return jsonify({"status": "error", "message": "Invalid state transition"}), 409

    # 4. Idempotency check — return existing result if key was seen before
    existing = PaymentRequest.query.filter_by(
        order_id=order_id, idempotency_key=idempotency_key
    ).first()
    if existing:
        return jsonify({"status": "ok", "data": serialize_order(order)}), 200

    # 5. Execute payment (all in one transaction)
    for item in order.items:
        product = Product.query.get(item.product_id)
        product.stock -= item.quantity

    payment = PaymentRequest(
        order_id=order_id,
        idempotency_key=idempotency_key,
        status='completed',
    )
    db.session.add(payment)

    order.status = 'paid'
    order.paid_at = datetime.utcnow()

    # 6. Unified commit
    db.session.commit()

    return jsonify({"status": "ok", "data": serialize_order(order)}), 200


# --- State machine routes (ATU-005) ---

@order_bp.route('/orders/<int:order_id>/ship', methods=['POST'])
def ship_order(order_id):
    """Transition an order from 'paid' to 'shipped'."""
    order = Order.query.get(order_id)
    if not order:
        return jsonify({"status": "error", "message": "Order not found"}), 404

    if not validate_transition(order, 'ship'):
        return jsonify({"status": "error", "message": "Invalid state transition"}), 409

    order.status = 'shipped'
    order.shipped_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"status": "ok", "data": serialize_order(order)}), 200


@order_bp.route('/orders/<int:order_id>/deliver', methods=['POST'])
def deliver_order(order_id):
    """Transition an order from 'shipped' to 'delivered'."""
    order = Order.query.get(order_id)
    if not order:
        return jsonify({"status": "error", "message": "Order not found"}), 404

    if not validate_transition(order, 'deliver'):
        return jsonify({"status": "error", "message": "Invalid state transition"}), 409

    order.status = 'delivered'
    order.delivered_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"status": "ok", "data": serialize_order(order)}), 200


@order_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    """Cancel an order in 'pending' or 'paid' status.

    When the current status is 'paid', the product stock is restored for
    every item in the order (inventory rollback).
    """
    order = Order.query.get(order_id)
    if not order:
        return jsonify({"status": "error", "message": "Order not found"}), 404

    if not validate_transition(order, 'cancel'):
        return jsonify({"status": "error", "message": "Invalid state transition"}), 409

    original_status = order.status
    order.status = 'cancelled'
    order.cancelled_at = datetime.utcnow()

    # Inventory rollback for paid orders
    if original_status == 'paid':
        for item in order.items:
            product = Product.query.get(item.product_id)
            product.stock += item.quantity

    db.session.commit()

    return jsonify({"status": "ok", "data": serialize_order(order)}), 200
