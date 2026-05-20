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


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order with validated product items."""
    data = request.get_json()
    if not data or 'user_id' not in data or 'items' not in data:
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400

    items = data['items']
    if not isinstance(items, list) or len(items) == 0:
        return jsonify({'status': 'error', 'message': 'Items must be a non-empty list'}), 400

    # Validate all products exist and stock is sufficient
    product_map = {}
    total_amount = 0.0
    for item in items:
        pid = item.get('product_id')
        qty = item.get('quantity')
        if pid is None or qty is None or qty <= 0:
            return jsonify({'status': 'error', 'message': 'Invalid item data'}), 400

        product = db.session.get(Product, pid)
        if product is None:
            return jsonify({'status': 'error', 'message': f'Product {pid} not found'}), 400
        if product.stock < qty:
            return jsonify({'status': 'error', 'message': f'Insufficient stock for product {pid}'}), 400

        product_map[pid] = product
        total_amount += product.price * qty

    # Create order and order items
    order = Order(user_id=data['user_id'], status='pending', total_amount=total_amount)
    db.session.add(order)
    db.session.flush()  # get order.id

    for item in items:
        pid = item['product_id']
        product = product_map[pid]
        order_item = OrderItem(
            order_id=order.id,
            product_id=pid,
            quantity=item['quantity'],
            unit_price=product.price,
        )
        db.session.add(order_item)

    db.session.commit()
    return jsonify({
        'status': 'ok',
        'data': {
            'id': order.id,
            'user_id': order.user_id,
            'status': order.status,
            'total_amount': order.total_amount,
            'created_at': order.created_at.isoformat() if order.created_at else None,
        }
    }), 201


@order_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    """Get order detail including items list."""
    order = db.session.get(Order, order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    return jsonify({
        'status': 'ok',
        'data': {
            'id': order.id,
            'user_id': order.user_id,
            'status': order.status,
            'total_amount': order.total_amount,
            'created_at': order.created_at.isoformat() if order.created_at else None,
            'items': [
                {
                    'id': item.id,
                    'product_id': item.product_id,
                    'quantity': item.quantity,
                    'unit_price': item.unit_price,
                }
                for item in order.items
            ],
        }
    }), 200


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders with optional user_id and status filters."""
    query = Order.query
    user_id = request.args.get('user_id')
    status = request.args.get('status')

    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    if status is not None:
        query = query.filter_by(status=status)

    orders = query.all()
    return jsonify({
        'status': 'ok',
        'data': [
            {
                'id': o.id,
                'user_id': o.user_id,
                'status': o.status,
                'total_amount': o.total_amount,
                'created_at': o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ]
    }), 200


@order_bp.route('/orders/<int:order_id>/pay', methods=['POST'])
def pay_order(order_id):
    """Pay for order (pending -> paid) with idempotency key."""
    order = db.session.get(Order, order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify({'status': 'error', 'message': 'Idempotency-Key header required'}), 400

    # Check for existing payment request with same key (idempotency)
    existing = PaymentRequest.query.filter_by(
        idempotency_key=idempotency_key, order_id=order_id
    ).first()
    if existing:
        if existing.status == 'paid':
            return jsonify({
                'status': 'ok',
                'data': {
                    'id': order.id,
                    'user_id': order.user_id,
                    'status': order.status,
                    'total_amount': order.total_amount,
                    'created_at': order.created_at.isoformat() if order.created_at else None,
                }
            }), 200
        # Different key for already-paid order is invalid state
        return jsonify({'status': 'error', 'message': 'Invalid state transition'}), 409

    if order.status != 'pending':
        return jsonify({'status': 'error', 'message': 'Invalid state transition'}), 409

    # Deduct stock for each order item
    for item in order.items:
        product = db.session.get(Product, item.product_id)
        product.stock -= item.quantity

    order.status = 'paid'
    order.paid_at = datetime.utcnow()

    payment = PaymentRequest(
        order_id=order.id,
        idempotency_key=idempotency_key,
        status='paid',
    )
    db.session.add(payment)
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': {
            'id': order.id,
            'user_id': order.user_id,
            'status': order.status,
            'total_amount': order.total_amount,
            'created_at': order.created_at.isoformat() if order.created_at else None,
        }
    }), 200


@order_bp.route('/orders/<int:order_id>/ship', methods=['POST'])
def ship_order(order_id):
    """Ship order (paid -> shipped)."""
    order = db.session.get(Order, order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status != 'paid':
        return jsonify({'status': 'error', 'message': 'Invalid state transition'}), 409

    order.status = 'shipped'
    order.shipped_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': {
            'id': order.id,
            'user_id': order.user_id,
            'status': order.status,
            'total_amount': order.total_amount,
            'created_at': order.created_at.isoformat() if order.created_at else None,
        }
    }), 200


@order_bp.route('/orders/<int:order_id>/deliver', methods=['POST'])
def deliver_order(order_id):
    """Deliver order (shipped -> delivered)."""
    order = db.session.get(Order, order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status != 'shipped':
        return jsonify({'status': 'error', 'message': 'Invalid state transition'}), 409

    order.status = 'delivered'
    order.delivered_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': {
            'id': order.id,
            'user_id': order.user_id,
            'status': order.status,
            'total_amount': order.total_amount,
            'created_at': order.created_at.isoformat() if order.created_at else None,
        }
    }), 200


@order_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    """Cancel order (pending/paid -> cancelled). Restores stock if paid."""
    order = db.session.get(Order, order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status not in ('pending', 'paid'):
        return jsonify({'status': 'error', 'message': 'Invalid state transition'}), 409

    # If order was paid, restore product stock
    if order.status == 'paid':
        for item in order.items:
            product = db.session.get(Product, item.product_id)
            product.stock += item.quantity

    order.status = 'cancelled'
    order.cancelled_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': {
            'id': order.id,
            'user_id': order.user_id,
            'status': order.status,
            'total_amount': order.total_amount,
            'created_at': order.created_at.isoformat() if order.created_at else None,
        }
    }), 200
