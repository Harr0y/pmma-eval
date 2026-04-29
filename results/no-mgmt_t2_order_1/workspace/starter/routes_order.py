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
from datetime import datetime

from app import db
from models import Product, Order, OrderItem, PaymentRequest

order_bp = Blueprint('order_bp', __name__)

VALID_TRANSITIONS = {
    'pending': {'pay', 'cancel'},
    'paid': {'ship', 'cancel'},
    'shipped': {'deliver'},
    'delivered': set(),
    'cancelled': set(),
}


def _serialize_order(order):
    return {
        'id': order.id,
        'user_id': order.user_id,
        'status': order.status,
        'total_amount': order.total_amount,
        'created_at': order.created_at.isoformat() if order.created_at else None,
    }


def _serialize_order_with_items(order):
    data = _serialize_order(order)
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
    body = request.get_json(force=True)
    user_id = body.get('user_id')
    items = body.get('items')

    if not user_id or not items:
        return jsonify({'status': 'error', 'message': 'user_id and items are required'}), 400

    if not isinstance(items, list) or len(items) == 0:
        return jsonify({'status': 'error', 'message': 'items must be a non-empty list'}), 400

    # Validate products and stock
    product_map = {}
    for item in items:
        pid = item.get('product_id')
        qty = item.get('quantity')
        if pid is None or qty is None or qty <= 0:
            return jsonify({'status': 'error', 'message': 'Each item must have product_id and positive quantity'}), 400

        product = Product.query.get(pid)
        if product is None:
            return jsonify({'status': 'error', 'message': f'Product {pid} not found'}), 400

        if product.stock < qty:
            return jsonify({'status': 'error', 'message': f'Insufficient stock for product {pid}'}), 400

        product_map[pid] = (product, qty)

    # Calculate total
    total_amount = 0.0
    for pid, (product, qty) in product_map.items():
        total_amount += product.price * qty

    # Create order
    order = Order(user_id=user_id, status='pending', total_amount=total_amount)
    db.session.add(order)
    db.session.flush()  # get order.id

    # Create order items
    for pid, (product, qty) in product_map.items():
        order_item = OrderItem(
            order_id=order.id,
            product_id=pid,
            quantity=qty,
            unit_price=product.price,
        )
        db.session.add(order_item)

    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_order(order)}), 201


@order_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    return jsonify({'status': 'ok', 'data': _serialize_order_with_items(order)})


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    query = Order.query

    user_id = request.args.get('user_id')
    if user_id:
        query = query.filter_by(user_id=user_id)

    status = request.args.get('status')
    if status:
        query = query.filter_by(status=status)

    orders = query.all()
    data = [_serialize_order_with_items(o) for o in orders]
    return jsonify({'status': 'ok', 'data': data})


@order_bp.route('/orders/<int:order_id>/pay', methods=['POST'])
def pay_order(order_id):
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    # Check idempotency key
    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify({'status': 'error', 'message': 'Idempotency-Key header is required'}), 400

    # Check for existing payment request with same key
    existing = PaymentRequest.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        # Idempotent: return success without re-processing
        return jsonify({'status': 'ok', 'data': _serialize_order(order)})

    # Validate state transition
    if 'pay' not in VALID_TRANSITIONS.get(order.status, set()):
        return jsonify({'status': 'error', 'message': f'Cannot pay order in status: {order.status}'}), 409

    # Deduct stock
    for item in order.items:
        product = Product.query.get(item.product_id)
        product.stock -= item.quantity

    # Update order status
    order.status = 'paid'
    order.paid_at = datetime.utcnow()

    # Record payment request
    payment = PaymentRequest(
        order_id=order.id,
        idempotency_key=idempotency_key,
        status='success',
    )
    db.session.add(payment)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_order(order)})


@order_bp.route('/orders/<int:order_id>/ship', methods=['POST'])
def ship_order(order_id):
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if 'ship' not in VALID_TRANSITIONS.get(order.status, set()):
        return jsonify({'status': 'error', 'message': f'Cannot ship order in status: {order.status}'}), 409

    order.status = 'shipped'
    order.shipped_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_order(order)})


@order_bp.route('/orders/<int:order_id>/deliver', methods=['POST'])
def deliver_order(order_id):
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if 'deliver' not in VALID_TRANSITIONS.get(order.status, set()):
        return jsonify({'status': 'error', 'message': f'Cannot deliver order in status: {order.status}'}), 409

    order.status = 'delivered'
    order.delivered_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_order(order)})


@order_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if 'cancel' not in VALID_TRANSITIONS.get(order.status, set()):
        return jsonify({'status': 'error', 'message': f'Cannot cancel order in status: {order.status}'}), 409

    # Restore stock if order was paid
    if order.status == 'paid':
        for item in order.items:
            product = Product.query.get(item.product_id)
            product.stock += item.quantity

    order.status = 'cancelled'
    order.cancelled_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_order(order)})
