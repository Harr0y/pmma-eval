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

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Blueprint, request, jsonify
from app import db
from models import Order, OrderItem, PaymentRequest, Product

order_bp = Blueprint('order_bp', __name__)


def _order_to_dict(order):
    """Serialize an order (without items) to a JSON-safe dict."""
    return {
        'id': order.id,
        'user_id': order.user_id,
        'status': order.status,
        'total_amount': order.total_amount,
        'created_at': order.created_at.isoformat() if order.created_at else None,
    }


def _order_with_items_to_dict(order):
    """Serialize an order including its items to a JSON-safe dict."""
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


# ── Order CRUD ──────────────────────────────────────────────


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order with validation."""
    body = request.get_json(silent=True) or {}

    user_id = body.get('user_id')
    items = body.get('items')

    if not user_id or not items:
        return jsonify({'status': 'error', 'message': 'user_id and items are required'}), 400

    # Validate each item and look up products
    order_items = []
    total_amount = 0.0
    for entry in items:
        pid = entry.get('product_id')
        qty = entry.get('quantity')
        if pid is None or qty is None or qty <= 0:
            return jsonify({'status': 'error', 'message': 'Each item must have product_id and positive quantity'}), 400

        product = Product.query.get(pid)
        if product is None:
            return jsonify({'status': 'error', 'message': f'Product {pid} not found'}), 400
        if product.stock < qty:
            return jsonify({'status': 'error', 'message': f'Insufficient stock for product {pid}'}), 400

        total_amount += product.price * qty
        order_items.append((product, qty))

    # Create order and order items
    order = Order(user_id=user_id, status='pending', total_amount=total_amount)
    db.session.add(order)
    db.session.flush()  # get order.id before creating items

    for product, qty in order_items:
        item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=qty,
            unit_price=product.price,
        )
        db.session.add(item)

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 201


@order_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    """Get a single order with its items."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404
    return jsonify({'status': 'ok', 'data': _order_with_items_to_dict(order)}), 200


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders, optionally filtered by user_id and/or status."""
    query = Order.query
    user_id = request.args.get('user_id')
    status = request.args.get('status')
    if user_id:
        query = query.filter(Order.user_id == user_id)
    if status:
        query = query.filter(Order.status == status)
    orders = query.all()
    return jsonify({'status': 'ok', 'data': [_order_to_dict(o) for o in orders]}), 200


# ── Order State Machine (ATU-003) ───────────────────────────

VALID_TRANSITIONS = {
    'pending': ['paid', 'cancelled'],
    'paid': ['shipped', 'cancelled'],
    'shipped': ['delivered'],
    'delivered': [],
    'cancelled': [],
}


@order_bp.route('/orders/<int:order_id>/pay', methods=['POST'])
def pay_order(order_id):
    """Pay for order (pending -> paid). Requires Idempotency-Key header."""
    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify({'status': 'error', 'message': 'Idempotency-Key header is required'}), 400

    # Idempotency check: if a PaymentRequest with this key exists, return current order state
    existing = PaymentRequest.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        order = Order.query.get(existing.order_id)
        return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 200

    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status != 'pending':
        return jsonify({'status': 'error', 'message': 'Invalid state transition'}), 409

    # Deduct stock for each item
    for item in order.items:
        product = Product.query.get(item.product_id)
        product.stock -= item.quantity

    order.status = 'paid'
    order.paid_at = db.func.now()

    payment = PaymentRequest(
        order_id=order.id,
        idempotency_key=idempotency_key,
        status='completed',
    )
    db.session.add(payment)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 200


@order_bp.route('/orders/<int:order_id>/ship', methods=['POST'])
def ship_order(order_id):
    """Ship order (paid -> shipped)."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status != 'paid':
        return jsonify({'status': 'error', 'message': 'Invalid state transition'}), 409

    order.status = 'shipped'
    order.shipped_at = db.func.now()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 200


@order_bp.route('/orders/<int:order_id>/deliver', methods=['POST'])
def deliver_order(order_id):
    """Deliver order (shipped -> delivered)."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status != 'shipped':
        return jsonify({'status': 'error', 'message': 'Invalid state transition'}), 409

    order.status = 'delivered'
    order.delivered_at = db.func.now()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 200


@order_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    """Cancel order (pending/paid -> cancelled). Restores stock if was paid."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status not in ('pending', 'paid'):
        return jsonify({'status': 'error', 'message': 'Invalid state transition'}), 409

    # Restore stock if order was paid
    if order.status == 'paid':
        for item in order.items:
            product = Product.query.get(item.product_id)
            product.stock += item.quantity

    order.status = 'cancelled'
    order.cancelled_at = db.func.now()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 200
