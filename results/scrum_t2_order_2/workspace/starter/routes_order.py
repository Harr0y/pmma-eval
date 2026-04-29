"""
T2 Order System — Order Routes

Implement order CRUD, state machine, and payment with idempotency.
Register as a Flask Blueprint named 'order_bp'.
"""

from datetime import datetime
from flask import Blueprint, request, jsonify
from app import db
from models import Product, Order, OrderItem, PaymentRequest

order_bp = Blueprint('order_bp', __name__)


def _order_to_dict(order):
    """Serialize an order with its items to a dict."""
    return {
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
    return jsonify({'status': 'ok', 'data': [_order_to_dict(o) for o in orders]})


@order_bp.route('/orders/<int:oid>', methods=['GET'])
def get_order(oid):
    order = Order.query.get(oid)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404
    return jsonify({'status': 'ok', 'data': _order_to_dict(order)})


@order_bp.route('/orders', methods=['POST'])
def create_order():
    body = request.get_json()
    if not body or 'user_id' not in body or 'items' not in body:
        return jsonify({'status': 'error', 'message': 'Missing required fields: user_id, items'}), 400

    user_id = body['user_id']
    items_data = body['items']

    if not items_data:
        return jsonify({'status': 'error', 'message': 'items must not be empty'}), 400

    # Validate all products exist and have sufficient stock
    product_map = {}
    for item in items_data:
        pid = item.get('product_id')
        qty = item.get('quantity', 0)
        product = Product.query.get(pid)
        if product is None:
            return jsonify({'status': 'error', 'message': f'Product {pid} not found'}), 400
        if product.stock < qty:
            return jsonify({'status': 'error', 'message': f'Insufficient stock for product {pid}'}), 400
        product_map[pid] = (product, qty)

    # Calculate total amount
    total_amount = sum(product.price * qty for product, qty in product_map.values())

    # Create order
    order = Order(user_id=user_id, status='pending', total_amount=total_amount)
    db.session.add(order)
    db.session.flush()  # get order.id before creating items

    # Create order items
    for pid, (product, qty) in product_map.items():
        oi = OrderItem(
            order_id=order.id,
            product_id=pid,
            quantity=qty,
            unit_price=product.price,
        )
        db.session.add(oi)

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 201


@order_bp.route('/orders/<int:oid>/pay', methods=['POST'])
def pay_order(oid):
    order = Order.query.get(oid)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify({'status': 'error', 'message': 'Idempotency-Key header is required'}), 400

    # Check if this idempotency key was already used
    existing = PaymentRequest.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        return jsonify({'status': 'ok', 'data': _order_to_dict(order)})

    if order.status != 'pending':
        return jsonify({'status': 'error', 'message': f'Cannot pay order in {order.status} status'}), 409

    # Deduct stock
    for item in order.items:
        product = Product.query.get(item.product_id)
        if product:
            product.stock -= item.quantity

    order.status = 'paid'
    order.paid_at = datetime.utcnow()

    # Record payment request for idempotency
    pr = PaymentRequest(order_id=order.id, idempotency_key=idempotency_key, status='paid')
    db.session.add(pr)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict(order)})


@order_bp.route('/orders/<int:oid>/ship', methods=['POST'])
def ship_order(oid):
    order = Order.query.get(oid)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404
    if order.status != 'paid':
        return jsonify({'status': 'error', 'message': f'Cannot ship order in {order.status} status'}), 409
    order.status = 'shipped'
    order.shipped_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'status': 'ok', 'data': _order_to_dict(order)})


@order_bp.route('/orders/<int:oid>/deliver', methods=['POST'])
def deliver_order(oid):
    order = Order.query.get(oid)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404
    if order.status != 'shipped':
        return jsonify({'status': 'error', 'message': f'Cannot deliver order in {order.status} status'}), 409
    order.status = 'delivered'
    order.delivered_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'status': 'ok', 'data': _order_to_dict(order)})


@order_bp.route('/orders/<int:oid>/cancel', methods=['POST'])
def cancel_order(oid):
    order = Order.query.get(oid)
    if order is None:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404
    if order.status not in ('pending', 'paid'):
        return jsonify({'status': 'error', 'message': f'Cannot cancel order in {order.status} status'}), 409

    # Restore stock if order was paid
    if order.status == 'paid':
        for item in order.items:
            product = Product.query.get(item.product_id)
            if product:
                product.stock += item.quantity

    order.status = 'cancelled'
    order.cancelled_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'status': 'ok', 'data': _order_to_dict(order)})
