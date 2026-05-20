"""
T2 Order System - Order Routes

Implement order CRUD, state machine, and payment with idempotency.
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
from app import db
from models import Product, Order, OrderItem, PaymentRequest

order_bp = Blueprint('order_bp', __name__)


def _order_to_dict(order):
    """Serialize an order to dict (without items)."""
    return {
        'id': order.id,
        'user_id': order.user_id,
        'status': order.status,
        'total_amount': order.total_amount,
        'created_at': order.created_at.isoformat() if order.created_at else None,
    }


def _order_with_items_to_dict(order):
    """Serialize an order with its items."""
    d = _order_to_dict(order)
    d['items'] = [
        {
            'id': item.id,
            'product_id': item.product_id,
            'quantity': item.quantity,
            'unit_price': item.unit_price,
        }
        for item in order.items
    ]
    return d


@order_bp.route('/orders', methods=['POST'])
def create_order():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'status': 'error', 'message': 'Request body must be JSON'}), 400

    user_id = body.get('user_id')
    items = body.get('items')

    if not user_id or not items:
        return jsonify({'status': 'error', 'message': 'user_id and items are required'}), 400

    # Validate products and stock
    order_items = []
    total_amount = 0.0
    for item in items:
        product_id = item.get('product_id')
        quantity = item.get('quantity')
        if product_id is None or quantity is None:
            return jsonify({'status': 'error', 'message': 'Each item needs product_id and quantity'}), 400

        product = Product.query.get(product_id)
        if not product:
            return jsonify({'status': 'error', 'message': f'Product {product_id} not found'}), 400

        if product.stock < quantity:
            return jsonify({'status': 'error', 'message': f'Insufficient stock for product {product_id}'}), 400

        order_items.append((product, quantity))
        total_amount += product.price * quantity

    # Create order
    order = Order(user_id=user_id, status='pending', total_amount=total_amount)
    db.session.add(order)
    db.session.flush()  # Get order.id

    # Create order items
    for product, quantity in order_items:
        oi = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=product.price,
        )
        db.session.add(oi)

    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 201


@order_bp.route('/orders/<int:oid>', methods=['GET'])
def get_order(oid):
    order = Order.query.get(oid)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    return jsonify({'status': 'ok', 'data': _order_with_items_to_dict(order)})


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
    return jsonify({'status': 'ok', 'data': [_order_to_dict(o) for o in orders]})


@order_bp.route('/orders/<int:oid>/pay', methods=['POST'])
def pay_order(oid):
    order = Order.query.get(oid)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify({'status': 'error', 'message': 'Idempotency-Key header is required'}), 400

    # Check for existing payment request with same key
    existing = PaymentRequest.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        # Idempotent: return the same result without re-processing
        return jsonify({'status': 'ok', 'data': _order_to_dict(order)})

    # State check
    if order.status != 'pending':
        return jsonify({'status': 'error', 'message': f'Cannot pay order in status: {order.status}'}), 409

    # Record payment request
    pr = PaymentRequest(
        order_id=order.id,
        idempotency_key=idempotency_key,
        status='completed',
    )
    db.session.add(pr)

    # Transition state
    order.status = 'paid'
    order.paid_at = datetime.utcnow()

    # Deduct stock
    for item in order.items:
        product = Product.query.get(item.product_id)
        if product:
            product.stock -= item.quantity

    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict(order)})


@order_bp.route('/orders/<int:oid>/ship', methods=['POST'])
def ship_order(oid):
    order = Order.query.get(oid)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status != 'paid':
        return jsonify({'status': 'error', 'message': f'Cannot ship order in status: {order.status}'}), 409

    order.status = 'shipped'
    order.shipped_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict(order)})


@order_bp.route('/orders/<int:oid>/deliver', methods=['POST'])
def deliver_order(oid):
    order = Order.query.get(oid)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status != 'shipped':
        return jsonify({'status': 'error', 'message': f'Cannot deliver order in status: {order.status}'}), 409

    order.status = 'delivered'
    order.delivered_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict(order)})


@order_bp.route('/orders/<int:oid>/cancel', methods=['POST'])
def cancel_order(oid):
    order = Order.query.get(oid)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status not in ('pending', 'paid'):
        return jsonify({'status': 'error', 'message': f'Cannot cancel order in status: {order.status}'}), 409

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
