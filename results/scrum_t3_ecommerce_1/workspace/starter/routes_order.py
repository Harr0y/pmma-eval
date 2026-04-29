"""
T3 E-commerce -- Order Routes

Implement order management routes.
Register as a Flask Blueprint named 'order_bp'.

Requirements:
- POST /orders -> Create order
  Request: {"product_id": int, "quantity": int, "origin": str(optional)}
  Response: {"status": "ok", "data": {"id": int, "user_id": int, "product_id": int,
            "quantity": int, "total_price": float, "origin": str}}
  - Must check stock before creating order
  - Must deduct stock on order creation (atomically)
  - total_price = product.price * quantity
  - origin defaults to 'web'
  - Errors: 400 if invalid, 401 if no user

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

from middleware import get_current_user, check_rate_limit, record_order
from models import User, Product, Order, db

order_bp = Blueprint('order_bp', __name__)


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order. Requires X-User-Id header."""
    user = get_current_user()
    if user is None:
        return jsonify({'status': 'error', 'message': 'Authentication required'}), 401

    # Rate limiting: check before processing, record only on success
    if check_rate_limit(user.id):
        return jsonify({'status': 'error', 'message': 'Rate limit exceeded'}), 429

    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Request body is required'}), 400

    product_id = data.get('product_id')
    quantity = data.get('quantity')
    origin = data.get('origin', 'web')

    if product_id is None or quantity is None:
        return jsonify({'status': 'error', 'message': 'product_id and quantity are required'}), 400

    quantity = int(quantity)
    product_id = int(product_id)

    if quantity <= 0:
        return jsonify({'status': 'error', 'message': 'quantity must be positive'}), 400

    # Atomic stock deduction: use filter + update with condition check
    # This ensures stock never goes negative even under concurrent access
    rows_updated = Product.query.filter(
        Product.id == product_id,
        Product.stock >= quantity
    ).update(
        {Product.stock: Product.stock - quantity},
        synchronize_session='fetch'
    )

    if rows_updated == 0:
        product = Product.query.get(product_id)
        if product is None:
            return jsonify({'status': 'error', 'message': 'Product not found'}), 404
        return jsonify({'status': 'error', 'message': 'Insufficient stock'}), 400

    # Fetch the product again to get price after the atomic update
    product = Product.query.get(product_id)
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

    # Record successful order for rate limiting
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
    """List orders. Admin sees all, regular user sees only their own."""
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
