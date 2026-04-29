"""
T2 Order System — Order Routes

Order state machine:
  pending -> paid -> shipped -> delivered
  pending/paid -> cancelled
"""

from datetime import datetime
from flask import Blueprint, request, jsonify
from models import Order, OrderItem, PaymentRequest, Product, db

order_bp = Blueprint('order_bp', __name__)

VALID_TRANSITIONS = {
    'pending': {'paid', 'cancelled'},
    'paid': {'shipped', 'cancelled'},
    'shipped': {'delivered'},
    'delivered': set(),
    'cancelled': set(),
}


def _serialize_order(order, include_items=False):
    data = {
        'id': order.id,
        'user_id': order.user_id,
        'status': order.status,
        'total_amount': order.total_amount,
        'created_at': order.created_at.isoformat() if order.created_at else None,
    }
    if include_items:
        data['items'] = [{
            'id': item.id,
            'product_id': item.product_id,
            'quantity': item.quantity,
            'unit_price': item.unit_price,
        } for item in order.items]
    return data


@order_bp.route('/orders', methods=['POST'])
def create_order():
    body = request.get_json(silent=True)
    if not body or 'user_id' not in body or 'items' not in body:
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400

    items = body['items']
    if not items:
        return jsonify({'status': 'error', 'message': 'Items list is empty'}), 400

    # Validate products and stock
    total_amount = 0.0
    order_items = []
    for item in items:
        pid = item.get('product_id')
        qty = item.get('quantity')
        product = Product.query.get(pid)
        if not product:
            return jsonify({'status': 'error', 'message': f'Product {pid} not found'}), 400
        if product.stock < qty:
            return jsonify({'status': 'error', 'message': f'Insufficient stock for product {pid}'}), 400
        order_items.append((product, qty))
        total_amount += product.price * qty

    # Create order
    order = Order(user_id=body['user_id'], status='pending', total_amount=total_amount)
    db.session.add(order)
    db.session.flush()  # get order.id

    for product, qty in order_items:
        oi = OrderItem(order_id=order.id, product_id=product.id, quantity=qty, unit_price=product.price)
        db.session.add(oi)

    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_order(order)}), 201


@order_bp.route('/orders/<int:oid>', methods=['GET'])
def get_order(oid):
    order = Order.query.get(oid)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    return jsonify({'status': 'ok', 'data': _serialize_order(order, include_items=True)})


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
    return jsonify({'status': 'ok', 'data': [_serialize_order(o) for o in orders]})


@order_bp.route('/orders/<int:oid>/pay', methods=['POST'])
def pay_order(oid):
    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify({'status': 'error', 'message': 'Idempotency-Key header required'}), 400

    order = Order.query.get(oid)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    # Check for existing payment request with same key (idempotency)
    existing = PaymentRequest.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        # Return current order state without re-processing
        return jsonify({'status': 'ok', 'data': _serialize_order(order)})

    # Validate state transition
    if 'paid' not in VALID_TRANSITIONS.get(order.status, set()):
        return jsonify({'status': 'error', 'message': f'Cannot transition from {order.status} to paid'}), 409

    # Deduct stock
    for item in order.items:
        product = Product.query.get(item.product_id)
        product.stock -= item.quantity

    # Update order
    order.status = 'paid'
    order.paid_at = datetime.utcnow()

    # Record payment request
    pr = PaymentRequest(order_id=order.id, idempotency_key=idempotency_key, status='completed')
    db.session.add(pr)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_order(order)})


@order_bp.route('/orders/<int:oid>/ship', methods=['POST'])
def ship_order(oid):
    order = Order.query.get(oid)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if 'shipped' not in VALID_TRANSITIONS.get(order.status, set()):
        return jsonify({'status': 'error', 'message': f'Cannot transition from {order.status} to shipped'}), 409

    order.status = 'shipped'
    order.shipped_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_order(order)})


@order_bp.route('/orders/<int:oid>/deliver', methods=['POST'])
def deliver_order(oid):
    order = Order.query.get(oid)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if 'delivered' not in VALID_TRANSITIONS.get(order.status, set()):
        return jsonify({'status': 'error', 'message': f'Cannot transition from {order.status} to delivered'}), 409

    order.status = 'delivered'
    order.delivered_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_order(order)})


@order_bp.route('/orders/<int:oid>/cancel', methods=['POST'])
def cancel_order(oid):
    order = Order.query.get(oid)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if 'cancelled' not in VALID_TRANSITIONS.get(order.status, set()):
        return jsonify({'status': 'error', 'message': f'Cannot transition from {order.status} to cancelled'}), 409

    # If order was paid, restore stock
    if order.status == 'paid':
        for item in order.items:
            product = Product.query.get(item.product_id)
            product.stock += item.quantity

    order.status = 'cancelled'
    order.cancelled_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_order(order)})
