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
  - Must deduct stock on order creation (atomically)
  - total_price = product.price * quantity
  - Rate limited: 1 order per 10s per user
  - Errors: 400 if invalid, 401 if no user, 429 if rate limited

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

from models import db, Product, Order
from middleware import get_current_user, check_rate_limit

order_bp = Blueprint('order_bp', __name__)


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create an order."""
    user = get_current_user()
    if not user:
        return jsonify({'status': 'error', 'message': 'Authentication required'}), 401

    # Rate limiting
    if not check_rate_limit(user.id):
        return jsonify({'status': 'error', 'message': 'Rate limit exceeded'}), 429

    data = request.get_json()
    if not data or 'product_id' not in data or 'quantity' not in data:
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400

    product_id = int(data['product_id'])
    quantity = int(data['quantity'])
    origin = data.get('origin', 'web')

    # Lock the product row to prevent concurrent stock issues
    product = db.session.query(Product).filter_by(id=product_id).with_for_update().first()
    if not product:
        return jsonify({'status': 'error', 'message': 'Product not found'}), 404

    if product.stock < quantity:
        return jsonify({'status': 'error', 'message': 'Insufficient stock'}), 400

    # Deduct stock atomically (within the locked row)
    product.stock -= quantity

    order = Order(
        user_id=user.id,
        product_id=product_id,
        quantity=quantity,
        total_price=product.price * quantity,
        origin=origin,
    )
    db.session.add(order)
    db.session.commit()

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
    """List orders. Admin sees all, regular user sees own."""
    user = get_current_user()
    if not user:
        return jsonify({'status': 'error', 'message': 'Authentication required'}), 401

    if user.role == 'admin':
        orders = Order.query.all()
    else:
        orders = Order.query.filter_by(user_id=user.id).all()

    data = [{
        'id': o.id,
        'user_id': o.user_id,
        'product_id': o.product_id,
        'quantity': o.quantity,
        'total_price': o.total_price,
        'origin': o.origin,
    } for o in orders]

    return jsonify({'status': 'ok', 'data': data}), 200
