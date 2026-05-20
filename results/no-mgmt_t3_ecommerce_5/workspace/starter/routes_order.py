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
  - total_price = product.price * quantity
  - Errors: 400 if invalid, 401 if no user, 429 if rate limited

- GET /orders -> List orders
  - Admin sees all orders
  - Regular user sees only their own orders
  Response: {"status": "ok", "data": [...]}

Use middleware.get_current_user() to get the authenticated user.
Use middleware.check_order_rate_limit(user_id) for rate limiting.
"""

from flask import Blueprint, request, jsonify
from sqlalchemy import text
from app import db
from models import Product, Order
import middleware

order_bp = Blueprint('order_bp', __name__)


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order with stock deduction and rate limiting."""
    user = middleware.get_current_user()
    if not user:
        return jsonify({'status': 'error', 'message': 'Authentication required'}), 401

    # Rate limiting: same user can only place 1 order per 10 seconds
    if not middleware.check_order_rate_limit(user.id):
        return middleware.rate_limit_response()

    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Invalid request body'}), 400

    product_id = data.get('product_id')
    quantity = data.get('quantity')
    origin = data.get('origin', 'web')

    if product_id is None or quantity is None:
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400

    quantity = int(quantity)

    # Atomic stock deduction: use UPDATE with WHERE to prevent race conditions
    result = db.session.execute(
        text('UPDATE product SET stock = stock - :qty WHERE id = :pid AND stock >= :qty'),
        {'qty': quantity, 'pid': product_id}
    )
    db.session.commit()

    if result.rowcount == 0:
        # Check if product exists at all
        product = db.session.get(Product, product_id)
        if product is None:
            return jsonify({'status': 'error', 'message': 'Product not found'}), 404
        # Product exists but insufficient stock
        return jsonify({'status': 'error', 'message': 'Insufficient stock'}), 400

    # Refresh product to get updated price
    product = db.session.get(Product, product_id)

    # Create order
    order = Order(
        user_id=user.id,
        product_id=product_id,
        quantity=quantity,
        total_price=product.price * quantity,
        origin=origin
    )
    db.session.add(order)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': {
        'id': order.id,
        'user_id': order.user_id,
        'product_id': order.product_id,
        'quantity': order.quantity,
        'total_price': order.total_price,
        'origin': order.origin
    }}), 201


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders. Admin sees all, regular users see their own."""
    user = middleware.get_current_user()
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
        'origin': o.origin
    } for o in orders]

    return jsonify({'status': 'ok', 'data': data}), 200
