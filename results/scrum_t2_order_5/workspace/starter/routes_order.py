"""
T2 Order System — Order Routes

Implement order CRUD, state machine, and payment with idempotency.
Register as a Flask Blueprint named 'order_bp'.

Order state machine:
  pending → paid → shipped → delivered
  pending/paid → cancelled

Requirements:
- POST /orders -> Create order
  Request: {"user_id": str, "items": [{"product_id": int, "quantity": int}, ...]}
  Response: {"status": "ok", "data": {"id": int, "user_id": str, "status": "pending",
            "total_amount": float, "created_at": str}}
  - Validates all products exist and stock is available
  - Creates OrderItem records for each product
  - total_amount = sum of (product.price * quantity) for all items
  Errors: 400 if invalid data, product not found, or insufficient stock

- GET /orders/<id> -> Get order with items
  Response: {"status": "ok", "data": {"id": int, "user_id": str, "status": str,
            "total_amount": float, "created_at": str,
            "items": [{"id": int, "product_id": int, "quantity": int, "unit_price": float}, ...]}}
  Errors: 404 if not found

- GET /orders -> List orders, filter by user_id and/or status
  Query params: user_id, status
  Response: {"status": "ok", "data": [...]}

- POST /orders/<id>/pay -> Pay for order (pending → paid)
  Header: Idempotency-Key (required)
  - Deducts stock from products
  - Records PaymentRequest for idempotency
  - Duplicate Idempotency-Key returns same result without re-processing
  Errors: 404 if order not found, 400 if no key, 409 if invalid state transition

- POST /orders/<id>/ship -> Ship order (paid → shipped)
  Errors: 404 if not found, 409 if invalid state

- POST /orders/<id>/deliver -> Deliver order (shipped → delivered)
  Errors: 404 if not found, 409 if invalid state

- POST /orders/<id>/cancel -> Cancel order (pending/paid → cancelled)
  - Restores product stock if order was paid
  Errors: 404 if not found, 409 if invalid state

IMPORTANT: This module works with models.py (Order, OrderItem, PaymentRequest, Product)
and routes_product.py. Stock deduction happens at payment time, not order creation.
"""

from flask import Blueprint, request, jsonify
from models import Product, Order, OrderItem, PaymentRequest, db
from datetime import datetime

order_bp = Blueprint('order_bp', __name__)


def _serialize_order(order, include_items=False):
    """Serialize an order to a dict."""
    data = {
        "id": order.id,
        "user_id": order.user_id,
        "status": order.status,
        "total_amount": order.total_amount,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }
    if include_items:
        data["items"] = [
            {
                "id": item.id,
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
            }
            for item in order.items
        ]
    return data


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order with stock validation and total calculation."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON"}), 400

    user_id = data.get('user_id')
    items = data.get('items')

    if not user_id or not items:
        return jsonify({"status": "error", "message": "Missing required fields: user_id, items"}), 400

    if not isinstance(items, list) or len(items) == 0:
        return jsonify({"status": "error", "message": "items must be a non-empty list"}), 400

    total_amount = 0.0
    order_items = []

    for item in items:
        product_id = item.get('product_id')
        quantity = item.get('quantity')

        if product_id is None or quantity is None:
            return jsonify({"status": "error", "message": "Each item must have product_id and quantity"}), 400

        quantity = int(quantity)
        if quantity <= 0:
            return jsonify({"status": "error", "message": "Quantity must be positive"}), 400

        product = Product.query.get(product_id)
        if product is None:
            return jsonify({"status": "error", "message": f"Product {product_id} not found"}), 400

        if product.stock < quantity:
            return jsonify({"status": "error", "message": f"Insufficient stock for product {product_id}"}), 400

        total_amount += product.price * quantity
        order_items.append((product, quantity))

    order = Order(user_id=user_id, status='pending', total_amount=total_amount)
    db.session.add(order)
    db.session.flush()

    for product, quantity in order_items:
        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=product.price,
        )
        db.session.add(order_item)

    db.session.commit()

    return jsonify({"status": "ok", "data": _serialize_order(order)}), 201


@order_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    """Get a single order by ID with its items."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({"status": "error", "message": "Order not found"}), 404

    return jsonify({"status": "ok", "data": _serialize_order(order, include_items=True)}), 200


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders, optionally filtered by user_id and/or status."""
    query = Order.query

    user_id = request.args.get('user_id')
    if user_id is not None:
        query = query.filter(Order.user_id == user_id)

    status = request.args.get('status')
    if status is not None:
        query = query.filter(Order.status == status)

    orders = query.all()
    return jsonify({"status": "ok", "data": [_serialize_order(o) for o in orders]}), 200


@order_bp.route('/orders/<int:order_id>/pay', methods=['POST'])
def pay_order(order_id):
    """Pay for an order: pending -> paid, with idempotency and stock deduction."""
    # 1. Check Idempotency-Key header
    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify({"status": "error", "message": "Idempotency-Key header is required"}), 400

    # 2. Find the order
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({"status": "error", "message": "Order not found"}), 404

    # 3. Check idempotency — if this key was already used, return previous result
    existing = PaymentRequest.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        return jsonify({"status": "ok", "data": _serialize_order(order)}), 200

    # 4. Only pending orders can be paid
    if order.status != 'pending':
        return jsonify({"status": "error", "message": "Order is not in pending status"}), 409

    # 5. Deduct stock for each order item
    for item in order.items:
        product = Product.query.get(item.product_id)
        product.stock -= item.quantity

    # 6. Update order status and timestamps
    order.status = 'paid'
    order.paid_at = datetime.utcnow()

    # 7. Record the payment request for idempotency
    payment = PaymentRequest(
        order_id=order.id,
        idempotency_key=idempotency_key,
        status='success',
    )
    db.session.add(payment)
    db.session.commit()

    return jsonify({"status": "ok", "data": _serialize_order(order)}), 200


@order_bp.route('/orders/<int:order_id>/ship', methods=['POST'])
def ship_order(order_id):
    """Ship order: paid -> shipped."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({"status": "error", "message": "Order not found"}), 404

    if order.status != 'paid':
        return jsonify({"status": "error", "message": "Order is not in paid status"}), 409

    order.status = 'shipped'
    order.shipped_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"status": "ok", "data": _serialize_order(order)}), 200


@order_bp.route('/orders/<int:order_id>/deliver', methods=['POST'])
def deliver_order(order_id):
    """Deliver order: shipped -> delivered."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({"status": "error", "message": "Order not found"}), 404

    if order.status != 'shipped':
        return jsonify({"status": "error", "message": "Order is not in shipped status"}), 409

    order.status = 'delivered'
    order.delivered_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"status": "ok", "data": _serialize_order(order)}), 200


@order_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    """Cancel order: pending/paid -> cancelled. Restores stock if order was paid."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({"status": "error", "message": "Order not found"}), 404

    if order.status not in ('pending', 'paid'):
        return jsonify({"status": "error", "message": "Order cannot be cancelled in current status"}), 409

    # If order was paid, restore product stock
    if order.status == 'paid':
        for item in order.items:
            product = Product.query.get(item.product_id)
            product.stock += item.quantity

    order.status = 'cancelled'
    order.cancelled_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"status": "ok", "data": _serialize_order(order)}), 200
