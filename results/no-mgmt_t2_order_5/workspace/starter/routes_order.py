"""
T2 Order System — Order Routes
"""

from datetime import datetime
from flask import Blueprint, request, jsonify
from app import db
from models import Product, Order, OrderItem, PaymentRequest

order_bp = Blueprint('order_bp', __name__)

VALID_TRANSITIONS = {
    'pending': ['paid', 'cancelled'],
    'paid': ['shipped', 'cancelled'],
    'shipped': ['delivered'],
}


def _order_to_dict(order):
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


def _order_summary(order):
    return {
        'id': order.id,
        'user_id': order.user_id,
        'status': order.status,
        'total_amount': order.total_amount,
        'created_at': order.created_at.isoformat() if order.created_at else None,
    }


@order_bp.route('/orders', methods=['POST'])
def create_order():
    data = request.get_json()
    if not data or 'user_id' not in data or 'items' not in data:
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400

    user_id = data['user_id']
    items = data['items']

    if not items:
        return jsonify({'status': 'error', 'message': 'No items provided'}), 400

    total_amount = 0.0
    order_items = []

    for item in items:
        product = Product.query.get(item['product_id'])
        if not product:
            return jsonify({'status': 'error', 'message': f'Product {item["product_id"]} not found'}), 400
        if product.stock < item['quantity']:
            return jsonify({'status': 'error', 'message': f'Insufficient stock for product {product.name}'}), 400
        total_amount += product.price * item['quantity']
        order_items.append((product, item['quantity']))

    order = Order(user_id=user_id, status='pending', total_amount=total_amount)
    db.session.add(order)
    db.session.flush()

    for product, quantity in order_items:
        oi = OrderItem(order_id=order.id, product_id=product.id, quantity=quantity, unit_price=product.price)
        db.session.add(oi)

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _order_summary(order)}), 201


@order_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404
    return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 200


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
    return jsonify({'status': 'ok', 'data': [_order_to_dict(o) for o in orders]}), 200


@order_bp.route('/orders/<int:order_id>/pay', methods=['POST'])
def pay_order(order_id):
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify({'status': 'error', 'message': 'Idempotency-Key header is required'}), 400

    # Check if this idempotency key was already used for this order
    existing = PaymentRequest.query.filter_by(order_id=order.id, idempotency_key=idempotency_key).first()
    if existing:
        return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 200

    if order.status != 'pending':
        return jsonify({'status': 'error', 'message': f'Cannot pay order in {order.status} state'}), 409

    # Deduct stock
    for item in order.items:
        product = Product.query.get(item.product_id)
        product.stock -= item.quantity

    order.status = 'paid'
    order.paid_at = datetime.utcnow()

    pr = PaymentRequest(order_id=order.id, idempotency_key=idempotency_key, status='success')
    db.session.add(pr)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 200


@order_bp.route('/orders/<int:order_id>/ship', methods=['POST'])
def ship_order(order_id):
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status not in VALID_TRANSITIONS or 'shipped' not in VALID_TRANSITIONS[order.status]:
        return jsonify({'status': 'error', 'message': f'Cannot ship order in {order.status} state'}), 409

    order.status = 'shipped'
    order.shipped_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 200


@order_bp.route('/orders/<int:order_id>/deliver', methods=['POST'])
def deliver_order(order_id):
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status not in VALID_TRANSITIONS or 'delivered' not in VALID_TRANSITIONS[order.status]:
        return jsonify({'status': 'error', 'message': f'Cannot deliver order in {order.status} state'}), 409

    order.status = 'delivered'
    order.delivered_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 200


@order_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status not in VALID_TRANSITIONS or 'cancelled' not in VALID_TRANSITIONS[order.status]:
        return jsonify({'status': 'error', 'message': f'Cannot cancel order in {order.status} state'}), 409

    # If paid, restore stock
    if order.status == 'paid':
        for item in order.items:
            product = Product.query.get(item.product_id)
            product.stock += item.quantity

    order.status = 'cancelled'
    order.cancelled_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _order_to_dict(order)}), 200
