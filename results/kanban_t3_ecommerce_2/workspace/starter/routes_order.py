"""
T3 E-commerce -- Order Routes

Implement order management routes.
Register as a Flask Blueprint named 'order_bp'.
"""

from flask import Blueprint, request, jsonify

from app import db
from models import Product, Order
from middleware import get_current_user, check_rate_limit

order_bp = Blueprint('order_bp', __name__)


@order_bp.route('/orders', methods=['POST'])
def create_order():
    user = get_current_user()
    if user is None:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    product_id = data.get('product_id')
    quantity = data.get('quantity')

    if product_id is None or quantity is None:
        return jsonify({'status': 'error', 'message': 'Missing product_id or quantity'}), 400

    product = db.session.get(Product, product_id)
    if product is None:
        return jsonify({'status': 'error', 'message': 'Product not found'}), 404

    if product.stock < quantity:
        return jsonify({'status': 'error', 'message': 'Insufficient stock'}), 400

    allowed, status_code = check_rate_limit(user.id)
    if not allowed:
        return jsonify({'status': 'error', 'message': 'Rate limit exceeded'}), status_code

    # Atomic stock deduction: expire cached state, then conditionally update
    db.session.expire(product)
    updated = db.session.query(Product).filter(
        Product.id == product_id,
        Product.stock >= quantity,
    ).update({'stock': Product.stock - quantity}, synchronize_session='fetch')

    if updated == 0:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'Insufficient stock'}), 400

    origin = data.get('origin', 'web')
    total_price = product.price * quantity

    order = Order(
        user_id=user.id,
        product_id=product_id,
        quantity=quantity,
        total_price=total_price,
        origin=origin,
    )
    db.session.add(order)
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': {
            'id': order.id,
            'user_id': order.user_id,
            'product_id': order.product_id,
            'quantity': order.quantity,
            'total_price': order.total_price,
            'origin': order.origin,
        },
    }), 201


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    user = get_current_user()
    if user is None:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    if user.role == 'admin':
        orders = Order.query.all()
    else:
        orders = Order.query.filter_by(user_id=user.id).all()

    return jsonify({
        'status': 'ok',
        'data': [
            {
                'id': o.id,
                'user_id': o.user_id,
                'product_id': o.product_id,
                'quantity': o.quantity,
                'total_price': o.total_price,
                'origin': o.origin,
            }
            for o in orders
        ],
    }), 200
