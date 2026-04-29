"""
T3 E-commerce — Order Routes

Implement order management routes.
Register as a Flask Blueprint named 'order_bp'.

Requirements:
- POST /orders -> Create order
  Request: {"product_id": int, "quantity": int, "origin": str (optional, default 'web')}
  Response: {"status": "ok", "data": {"id": int, "user_id": int, "product_id": int,
            "quantity": int, "total_price": float, "origin": str}}
  - Must check stock before creating order
  - Must deduct stock atomically on order creation
  - Rate limited: 1 order per 10 seconds per user
  - total_price = product.price * quantity
  - Errors: 400 if invalid, 401 if no user, 429 if rate-limited

- GET /orders -> List orders
  - Admin sees all orders
  - Regular user sees only their own orders
  Response: {"status": "ok", "data": [...]}

Use middleware.get_current_user() to get the authenticated user.
"""

from flask import Blueprint, request, jsonify
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from models import Product, Order
from middleware import get_current_user, check_rate_limit, record_order

order_bp = Blueprint('order_bp', __name__)


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create an order. Requires authenticated user."""
    user = get_current_user()
    if user is None:
        return jsonify({'status': 'error', 'message': 'Authentication required'}), 401

    # Rate limit check
    allowed, error_response = check_rate_limit(user.id)
    if not allowed:
        return error_response

    body = request.get_json()
    if not body or 'product_id' not in body or 'quantity' not in body:
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400

    from app import db

    product_id = int(body['product_id'])
    quantity = int(body['quantity'])
    origin = body.get('origin', 'web')

    product = Product.query.get(product_id)
    if product is None:
        return jsonify({'status': 'error', 'message': 'Product not found'}), 404

    # Atomic stock deduction using conditional UPDATE
    rows_affected = db.session.execute(
        db.text('UPDATE product SET stock = stock - :qty WHERE id = :pid AND stock >= :qty'),
        {'qty': quantity, 'pid': product_id}
    ).rowcount

    if rows_affected == 0:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'Insufficient stock'}), 400

    # Refresh product to get updated price
    db.session.refresh(product)
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

    # Record order timestamp for rate limiting
    record_order(user.id)

    return jsonify({'status': 'ok', 'data': {
        'id': order.id,
        'user_id': order.user_id,
        'product_id': order.product_id,
        'quantity': order.quantity,
        'total_price': order.total_price,
        'origin': order.origin,
    }}), 201


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders. Admin sees all, regular user sees own orders."""
    user = get_current_user()
    if user is None:
        return jsonify({'status': 'error', 'message': 'Authentication required'}), 401

    if user.role == 'admin':
        orders = Order.query.all()
    else:
        orders = Order.query.filter_by(user_id=user.id).all()

    data = [
        {
            'id': o.id,
            'user_id': o.user_id,
            'product_id': o.product_id,
            'quantity': o.quantity,
            'total_price': o.total_price,
            'origin': o.origin,
        }
        for o in orders
    ]
    return jsonify({'status': 'ok', 'data': data}), 200
