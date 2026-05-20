"""
T3 E-commerce — Order Routes

Implement order management routes.
Register as a Flask Blueprint named 'order_bp'.

Requirements:
- POST /orders -> Create order
  Request: {"product_id": int, "quantity": int, "origin": str (optional)}
  Response: {"status": "ok", "data": {"id": int, "user_id": int, "product_id": int,
            "quantity": int, "total_price": float, "origin": str}}
  - Must check stock before creating order
  - Must deduct stock on order creation
  - total_price = product.price * quantity
  - Errors: 400 if invalid, 401 if no user

- GET /orders -> List orders
  - Admin sees all orders
  - Regular user sees only their own orders
  Response: {"status": "ok", "data": [...]}

Use middleware.get_current_user() to get the authenticated user.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Blueprint, request, jsonify
from sqlalchemy import text
from app import db
from models import Product, Order
from middleware import get_current_user, check_rate_limit, record_order

order_bp = Blueprint('order_bp', __name__)


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order. Requires authentication."""
    user = get_current_user()
    if user is None:
        return jsonify({'status': 'error', 'message': 'Authentication required'}), 401

    # Rate limit check: one order per user per 10 seconds
    allowed, remaining = check_rate_limit(user.id)
    if not allowed:
        return jsonify({
            'status': 'error',
            'message': f'Rate limit exceeded. Try again in {remaining} seconds.',
        }), 429

    data = request.get_json()
    if not data or 'product_id' not in data or 'quantity' not in data:
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400

    product_id = data['product_id']
    quantity = data['quantity']

    product = Product.query.get(product_id)
    if product is None:
        return jsonify({'status': 'error', 'message': 'Product not found'}), 404

    # Atomic stock deduction: use database-level UPDATE to prevent race conditions
    result = db.session.execute(
        text("UPDATE product SET stock = stock - :qty WHERE id = :pid AND stock >= :qty"),
        {"qty": quantity, "pid": product_id}
    )
    if result.rowcount == 0:
        return jsonify({'status': 'error', 'message': 'Insufficient stock'}), 400

    db.session.refresh(product)

    # Calculate total price
    total_price = product.price * quantity

    # Get origin from request, default to 'web'
    origin = data.get('origin', 'web')

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
    """List orders. Admin sees all, regular users see only their own."""
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
