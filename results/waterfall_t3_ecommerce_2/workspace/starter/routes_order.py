"""
T3 E-commerce — Order Routes

Implement order management routes.
Register as a Flask Blueprint named 'order_bp'.

Requirements:
- POST /orders -> Create order
  Request: {"product_id": int, "quantity": int, "origin": str (optional)}
  Response: {"status": "ok", "data": order.to_dict()}
  - Must atomically deduct stock using conditional UPDATE
  - Must check rate limit before ordering
  - total_price = product.price * quantity
  - origin defaults to 'web'
  - Errors: 400 if invalid, 401 if no user, 429 if rate limited

- GET /orders -> List orders
  - Admin sees all orders
  - Regular user sees only their own orders
  Response: {"status": "ok", "data": [...]}

Use middleware.get_current_user() to get the authenticated user.
"""

from flask import Blueprint, request, jsonify
from sqlalchemy import update
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import db
from models import Product, Order
from middleware import get_current_user, check_rate_limit, record_order

order_bp = Blueprint('order_bp', __name__)


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order. Requires authenticated user."""
    user = get_current_user()
    if user is None:
        return jsonify({
            'status': 'error',
            'message': 'Authentication required: missing or invalid X-User-Id header',
        }), 401

    # Check rate limit
    allowed, _ = check_rate_limit(user.id)
    if not allowed:
        return jsonify({
            'status': 'error',
            'message': 'Rate limit exceeded',
        }), 429

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({
            'status': 'error',
            'message': 'Request body must be valid JSON',
        }), 400

    # Validate required fields
    product_id = data.get('product_id')
    quantity = data.get('quantity')
    origin = data.get('origin', 'web')

    if product_id is None:
        return jsonify({
            'status': 'error',
            'message': 'Missing required field: product_id',
        }), 400

    if quantity is None:
        return jsonify({
            'status': 'error',
            'message': 'Missing required field: quantity',
        }), 400

    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        return jsonify({
            'status': 'error',
            'message': 'Invalid quantity: must be a positive integer',
        }), 400

    # Atomically deduct stock using conditional UPDATE
    result = db.session.execute(
        update(Product)
        .where(Product.id == product_id, Product.stock >= quantity)
        .values(stock=Product.stock - quantity)
    )
    if result.rowcount == 0:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': 'Insufficient stock or product not found',
        }), 400

    # Fetch the product to get the price (stock already deducted)
    product = db.session.get(Product, product_id)

    order = Order(
        user_id=user.id,
        product_id=product_id,
        quantity=quantity,
        total_price=product.price * quantity,
        origin=origin,
    )
    db.session.add(order)
    db.session.commit()

    # Record order timestamp for rate limiting
    record_order(user.id)

    return jsonify({
        'status': 'ok',
        'data': order.to_dict(),
    }), 201


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders. Admin sees all, regular user sees only own."""
    user = get_current_user()
    if user is None:
        return jsonify({
            'status': 'error',
            'message': 'Authentication required: missing or invalid X-User-Id header',
        }), 401

    if user.role == 'admin':
        orders = Order.query.all()
    else:
        orders = Order.query.filter_by(user_id=user.id).all()

    return jsonify({
        'status': 'ok',
        'data': [o.to_dict() for o in orders],
    }), 200
