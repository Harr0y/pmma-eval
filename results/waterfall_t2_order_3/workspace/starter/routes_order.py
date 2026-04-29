"""
T2 Order System — Order Routes

Implement order CRUD, state machine, and payment with idempotency.
Register as a Flask Blueprint named 'order_bp'.

Order state machine:
  pending -> paid -> shipped -> delivered
  pending/paid -> cancelled
"""

from flask import Blueprint, request, jsonify
from models import Product, Order, OrderItem, PaymentRequest
from app import db
from datetime import datetime

order_bp = Blueprint('order_bp', __name__)

# State machine: valid transitions from each status (design.md Section 3)
VALID_TRANSITIONS = {
    'pending': {'paid', 'cancelled'},
    'paid': {'shipped', 'cancelled'},
    'shipped': {'delivered'},
    'delivered': set(),
    'cancelled': set(),
}


def order_to_dict(o):
    """Serialize an Order model instance to a dict (design.md Section 7)."""
    return {
        "id": o.id,
        "user_id": o.user_id,
        "status": o.status,
        "total_amount": o.total_amount,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        "shipped_at": o.shipped_at.isoformat() if o.shipped_at else None,
        "delivered_at": o.delivered_at.isoformat() if o.delivered_at else None,
        "cancelled_at": o.cancelled_at.isoformat() if o.cancelled_at else None,
        "items": [
            {"id": i.id, "product_id": i.product_id, "quantity": i.quantity, "unit_price": i.unit_price}
            for i in o.items
        ],
    }


# ------------------------------------------------------------------
# 2.2.1 POST /orders — Create Order
# ------------------------------------------------------------------
@order_bp.route('/orders', methods=['POST'])
def create_order():
    data = request.get_json()
    # Validate required fields
    if not data or 'user_id' not in data or 'items' not in data or not data['items']:
        return jsonify({"status": "error", "message": "Missing required fields: user_id and items"}), 400

    user_id = data['user_id']
    items = data['items']
    total_amount = 0.0
    order_items = []

    # Validate each item: product exists and stock is sufficient
    for item in items:
        product = Product.query.get(item['product_id'])
        if not product:
            return jsonify({"status": "error", "message": f"Product {item['product_id']} not found"}), 400
        if product.stock < item['quantity']:
            return jsonify({"status": "error", "message": f"Insufficient stock for product {item['product_id']}"}), 400
        total_amount += product.price * item['quantity']
        order_items.append((product, item['quantity']))

    # Create Order (status='pending') — do NOT deduct stock (design.md Section 4)
    order = Order(user_id=user_id, status='pending', total_amount=total_amount)
    db.session.add(order)
    db.session.flush()  # get order.id before creating OrderItems

    # Create OrderItem records (unit_price = product.price at creation time)
    for product, quantity in order_items:
        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=product.price,
        )
        db.session.add(order_item)

    db.session.commit()
    return jsonify({"status": "ok", "data": order_to_dict(order)}), 201


# ------------------------------------------------------------------
# 2.2.2 GET /orders/<id> — Get Order Detail
# ------------------------------------------------------------------
@order_bp.route('/orders/<int:id>', methods=['GET'])
def get_order(id):
    order = Order.query.get(id)
    if not order:
        return jsonify({"status": "error", "message": "Order not found"}), 404
    return jsonify({"status": "ok", "data": order_to_dict(order)}), 200


# ------------------------------------------------------------------
# 2.2.3 GET /orders — List/Filter Orders
# ------------------------------------------------------------------
@order_bp.route('/orders', methods=['GET'])
def list_orders():
    query = Order.query
    user_id = request.args.get('user_id')
    status = request.args.get('status')
    if user_id:
        query = query.filter(Order.user_id == user_id)
    if status:
        query = query.filter(Order.status == status)
    orders = query.all()
    return jsonify({"status": "ok", "data": [order_to_dict(o) for o in orders]}), 200


# ------------------------------------------------------------------
# 2.2.4 POST /orders/<id>/pay — Pay Order (pending -> paid)
# ------------------------------------------------------------------
@order_bp.route('/orders/<int:id>/pay', methods=['POST'])
def pay_order(id):
    order = Order.query.get(id)
    if not order:
        return jsonify({"status": "error", "message": "Order not found"}), 404

    # Check Idempotency-Key header — required (design.md Section 2.2.4)
    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify({"status": "error", "message": "Idempotency-Key header is required"}), 400

    # Idempotency check BEFORE state check (design.md Section 3 special case)
    existing_payment = PaymentRequest.query.filter_by(idempotency_key=idempotency_key).first()
    if existing_payment:
        db.session.refresh(order)
        return jsonify({"status": "ok", "data": order_to_dict(order)}), 200

    # State check
    if 'paid' not in VALID_TRANSITIONS.get(order.status, set()):
        return jsonify({"status": "error", "message": f"Invalid state transition from {order.status}"}), 409

    # Deduct stock for each item
    for item in order.items:
        product = Product.query.get(item.product_id)
        product.stock -= item.quantity

    # Create PaymentRequest record
    payment = PaymentRequest(order_id=order.id, idempotency_key=idempotency_key, status='completed')
    db.session.add(payment)

    # Update order status
    order.status = 'paid'
    order.paid_at = datetime.utcnow()

    db.session.commit()
    return jsonify({"status": "ok", "data": order_to_dict(order)}), 200


# ------------------------------------------------------------------
# 2.2.5 POST /orders/<id>/ship — Ship Order (paid -> shipped)
# ------------------------------------------------------------------
@order_bp.route('/orders/<int:id>/ship', methods=['POST'])
def ship_order(id):
    order = Order.query.get(id)
    if not order:
        return jsonify({"status": "error", "message": "Order not found"}), 404

    if 'shipped' not in VALID_TRANSITIONS.get(order.status, set()):
        return jsonify({"status": "error", "message": f"Invalid state transition from {order.status}"}), 409

    order.status = 'shipped'
    order.shipped_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"status": "ok", "data": order_to_dict(order)}), 200


# ------------------------------------------------------------------
# 2.2.6 POST /orders/<id>/deliver — Deliver Order (shipped -> delivered)
# ------------------------------------------------------------------
@order_bp.route('/orders/<int:id>/deliver', methods=['POST'])
def deliver_order(id):
    order = Order.query.get(id)
    if not order:
        return jsonify({"status": "error", "message": "Order not found"}), 404

    if 'delivered' not in VALID_TRANSITIONS.get(order.status, set()):
        return jsonify({"status": "error", "message": f"Invalid state transition from {order.status}"}), 409

    order.status = 'delivered'
    order.delivered_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"status": "ok", "data": order_to_dict(order)}), 200


# ------------------------------------------------------------------
# 2.2.7 POST /orders/<id>/cancel — Cancel Order (pending/paid -> cancelled)
# ------------------------------------------------------------------
@order_bp.route('/orders/<int:id>/cancel', methods=['POST'])
def cancel_order(id):
    order = Order.query.get(id)
    if not order:
        return jsonify({"status": "error", "message": "Order not found"}), 404

    if 'cancelled' not in VALID_TRANSITIONS.get(order.status, set()):
        return jsonify({"status": "error", "message": f"Invalid state transition from {order.status}"}), 409

    # If order was paid, restore stock for each item (design.md Section 2.2.7)
    if order.status == 'paid':
        for item in order.items:
            product = Product.query.get(item.product_id)
            product.stock += item.quantity

    order.status = 'cancelled'
    order.cancelled_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"status": "ok", "data": order_to_dict(order)}), 200
