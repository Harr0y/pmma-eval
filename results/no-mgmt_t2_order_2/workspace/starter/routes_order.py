"""
T2 Order System - Order Routes

Implement order CRUD, state machine, and payment with idempotency.
Register as a Flask Blueprint named 'order_bp'.

Order state machine:
  pending -> paid -> shipped -> delivered
  pending/paid -> cancelled
"""

from datetime import datetime
from flask import Blueprint, request, jsonify
from models import db, Product, Order, OrderItem, PaymentRequest

order_bp = Blueprint('order_bp', __name__)

VALID_TRANSITIONS = {
    'pending': ['paid', 'cancelled'],
    'paid': ['shipped', 'cancelled'],
    'shipped': ['delivered'],
    'delivered': [],
    'cancelled': [],
}


def _order_to_dict(order):
    return {
        'id': order.id,
        'user_id': order.user_id,
        'status': order.status,
        'total_amount': order.total_amount,
        'created_at': order.created_at.isoformat() if order.created_at else None,
    }


def _order_detail_dict(order):
    d = _order_to_dict(order)
    d['items'] = [{
        'id': item.id,
        'product_id': item.product_id,
        'quantity': item.quantity,
        'unit_price': item.unit_price,
    } for item in order.items]
    return d


@order_bp.route('/orders', methods=['POST'])
def create_order():
    data = request.get_json()
    if not data or 'user_id' not in data or 'items' not in data:
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400

    items = data['items']
    if not items:
        return jsonify({'status': 'error', 'message': 'Items cannot be empty'}), 400

    # Validate products and stock
    order_items = []
    total_amount = 0.0
    for item in items:
        product = Product.query.get(item['product_id'])
        if not product:
            return jsonify({'status': 'error', 'message': f'Product {item["product_id"]} not found'}), 400
        if product.stock < item['quantity']:
            return jsonify({'status': 'error', 'message': f'Insufficient stock for product {item["product_id"]}'}), 400
        order_items.append((product, item['quantity']))
        total_amount += product.price * item['quantity']

    # Create order
    order = Order(user_id=data['user_id'], status='pending', total_amount=total_amount)
    db.session.add(order)
    db.session.flush()  # Get order.id

    for product, quantity in order_items:
        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=product.price,
        )
        db.session.add(order_item)

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 201


@order_bp.route('/orders/<int:oid>', methods=['GET'])
def get_order(oid):
    order = Order.query.get(oid)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    return jsonify({'status': 'ok', 'data': _order_detail_dict(order)}), 200


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    query = Order.query
    user_id = request.args.get('user_id')
    status = request.args.get('status')
    if user_id:
        query = query.filter_by(user_id=user_id)
    if status:
        query = query.filter_by(status=status)
    orders = query.all()
    return jsonify({'status': 'ok', 'data': [_order_to_dict(o) for o in orders]}), 200


@order_bp.route('/orders/<int:oid>/pay', methods=['POST'])
def pay_order(oid):
    order = Order.query.get(oid)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify({'status': 'error', 'message': 'Idempotency-Key header required'}), 400

    # Check for duplicate idempotency key
    existing = PaymentRequest.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 200

    # Validate state transition
    if 'paid' not in VALID_TRANSITIONS.get(order.status, []):
        return jsonify({'status': 'error', 'message': f'Cannot transition from {order.status} to paid'}), 409

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

    return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 200


@order_bp.route('/orders/<int:oid>/ship', methods=['POST'])
def ship_order(oid):
    order = Order.query.get(oid)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if 'shipped' not in VALID_TRANSITIONS.get(order.status, []):
        return jsonify({'status': 'error', 'message': f'Cannot transition from {order.status} to shipped'}), 409

    order.status = 'shipped'
    order.shipped_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 200


@order_bp.route('/orders/<int:oid>/deliver', methods=['POST'])
def deliver_order(oid):
    order = Order.query.get(oid)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if 'delivered' not in VALID_TRANSITIONS.get(order.status, []):
        return jsonify({'status': 'error', 'message': f'Cannot transition from {order.status} to delivered'}), 409

    order.status = 'delivered'
    order.delivered_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 200


@order_bp.route('/orders/<int:oid>/cancel', methods=['POST'])
def cancel_order(oid):
    order = Order.query.get(oid)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if 'cancelled' not in VALID_TRANSITIONS.get(order.status, []):
        return jsonify({'status': 'error', 'message': f'Cannot transition from {order.status} to cancelled'}), 409

    # Restore stock if order was paid
    if order.status == 'paid':
        for item in order.items:
            product = Product.query.get(item.product_id)
            product.stock += item.quantity

    order.status = 'cancelled'
    order.cancelled_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 200
