"""
T2 Order System — Order Routes

Implement order CRUD, state machine, and payment with idempotency.
Register as a Flask Blueprint named 'order_bp'.

Order state machine:
  pending -> paid -> shipped -> delivered
  pending/paid -> cancelled

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

- POST /orders/<id>/pay -> Pay for order (pending -> paid)
  Header: Idempotency-Key (required)
  - Deducts stock from products
  - Records PaymentRequest for idempotency
  - Duplicate Idempotency-Key returns same result without re-processing
  Errors: 404 if order not found, 400 if no key, 409 if invalid state transition

- POST /orders/<id>/ship -> Ship order (paid -> shipped)
  Errors: 404 if not found, 409 if invalid state

- POST /orders/<id>/deliver -> Deliver order (shipped -> delivered)
  Errors: 404 if not found, 409 if invalid state

- POST /orders/<id>/cancel -> Cancel order (pending/paid -> cancelled)
  - Restores product stock if order was paid
  Errors: 404 if not found, 409 if invalid state

IMPORTANT: This module works with models.py (Order, OrderItem, PaymentRequest, Product)
and routes_product.py. Stock deduction happens at payment time, not order creation.
"""

from flask import Blueprint, request, jsonify
from app import db
from models import Order, OrderItem, Product, PaymentRequest
from datetime import datetime

order_bp = Blueprint('order_bp', __name__)


def _order_to_dict(order):
    """Serialize an Order to dict (without items)."""
    return {
        'id': order.id,
        'user_id': order.user_id,
        'status': order.status,
        'total_amount': order.total_amount,
        'created_at': order.created_at.isoformat() if order.created_at else None,
    }


def _order_to_dict_with_items(order):
    """Serialize an Order with its items."""
    data = _order_to_dict(order)
    data['items'] = [
        {
            'id': item.id,
            'product_id': item.product_id,
            'quantity': item.quantity,
            'unit_price': item.unit_price,
        }
        for item in order.items
    ]
    return data


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order with items, validate product existence and stock."""
    data = request.get_json()
    if not data or 'user_id' not in data or 'items' not in data:
        return jsonify({'status': 'error', 'message': 'Missing required fields: user_id, items'}), 400

    user_id = data['user_id']
    items = data['items']

    if not items:
        return jsonify({'status': 'error', 'message': 'items must not be empty'}), 400

    # Validate products and compute total
    total_amount = 0.0
    validated_items = []
    for item in items:
        product_id = item.get('product_id')
        quantity = item.get('quantity')
        if product_id is None or quantity is None or quantity <= 0:
            return jsonify({'status': 'error', 'message': 'Each item must have product_id and positive quantity'}), 400

        product = Product.query.get(product_id)
        if product is None:
            return jsonify({'status': 'error', 'message': f'Product {product_id} not found'}), 400
        if product.stock < quantity:
            return jsonify({'status': 'error', 'message': f'Insufficient stock for product {product_id}'}), 400

        validated_items.append((product, quantity))
        total_amount += product.price * quantity

    # Create order and order items
    order = Order(user_id=user_id, status='pending', total_amount=total_amount)
    db.session.add(order)
    db.session.flush()  # get order.id before committing

    for product, quantity in validated_items:
        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=product.price,
        )
        db.session.add(order_item)

    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict_with_items(order)}), 201


@order_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    """Get a single order by ID with its items."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    return jsonify({'status': 'ok', 'data': _order_to_dict_with_items(order)}), 200


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders with optional filtering by user_id and/or status."""
    query = Order.query

    user_id = request.args.get('user_id')
    if user_id is not None:
        query = query.filter(Order.user_id == user_id)

    status = request.args.get('status')
    if status is not None:
        query = query.filter(Order.status == status)

    orders = query.order_by(Order.id).all()
    return jsonify({'status': 'ok', 'data': [_order_to_dict(o) for o in orders]}), 200


# ============================================================
# State machine routes (implemented by ATU-003, ATU-004)
# ============================================================

@order_bp.route('/orders/<int:order_id>/pay', methods=['POST'])
def pay_order(order_id):
    """Pay for an order (pending -> paid). Requires Idempotency-Key header."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify({'status': 'error', 'message': 'Idempotency-Key header is required'}), 400

    # Check for duplicate idempotency key
    existing = PaymentRequest.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        return jsonify({'status': 'ok', 'data': _order_to_dict_with_items(order)}), 200

    # Validate state transition
    if order.status != 'pending':
        return jsonify({'status': 'error', 'message': f'Cannot pay order in status: {order.status}'}), 409

    # Deduct stock from products
    for item in order.items:
        product = Product.query.get(item.product_id)
        product.stock -= item.quantity

    # Update order status
    order.status = 'paid'
    order.paid_at = datetime.utcnow()

    # Record payment request for idempotency
    payment = PaymentRequest(
        order_id=order.id,
        idempotency_key=idempotency_key,
        status='paid',
    )
    db.session.add(payment)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict_with_items(order)}), 200


@order_bp.route('/orders/<int:order_id>/ship', methods=['POST'])
def ship_order(order_id):
    """Ship an order (paid -> shipped)."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status != 'paid':
        return jsonify({'status': 'error', 'message': f'Cannot ship order in status: {order.status}'}), 409

    order.status = 'shipped'
    order.shipped_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict_with_items(order)}), 200


@order_bp.route('/orders/<int:order_id>/deliver', methods=['POST'])
def deliver_order(order_id):
    """Deliver an order (shipped -> delivered)."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status != 'shipped':
        return jsonify({'status': 'error', 'message': f'Cannot deliver order in status: {order.status}'}), 409

    order.status = 'delivered'
    order.delivered_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict_with_items(order)}), 200


@order_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    """Cancel an order (pending/paid -> cancelled). Restores stock if order was paid."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status not in ('pending', 'paid'):
        return jsonify({'status': 'error', 'message': f'Cannot cancel order in status: {order.status}'}), 409

    # If order was paid, restore product stock
    if order.status == 'paid':
        for item in order.items:
            product = Product.query.get(item.product_id)
            product.stock += item.quantity

    order.status = 'cancelled'
    order.cancelled_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict_with_items(order)}), 200
