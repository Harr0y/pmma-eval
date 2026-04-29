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
  - Must deduct stock on order creation (with FOR UPDATE locking)
  - total_price = product.price * quantity
  - origin defaults to 'web'
  - Rate limit: 10-second window per user
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

from middleware import get_current_user, check_rate_limit, record_order_time
from models import Product, Order
from app import db

order_bp = Blueprint('order_bp', __name__)


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order. Requires authentication (any role). Rate-limited to 1 order per 10s per user."""
    user = get_current_user()
    if user is None:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    if not check_rate_limit(user.id):
        return jsonify({"status": "error", "message": "Too many requests"}), 429

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON"}), 400

    product_id = data.get('product_id')
    quantity = data.get('quantity')

    if product_id is None or quantity is None:
        return jsonify({"status": "error", "message": "Missing required fields: product_id, quantity"}), 400

    # Validate quantity is a positive integer
    if not isinstance(quantity, int) or quantity <= 0:
        return jsonify({"status": "error", "message": "Quantity must be a positive integer"}), 400

    # Atomic stock deduction using SELECT FOR UPDATE (no-op on SQLite but safe)
    product = Product.query.filter_by(id=product_id).with_for_update().first()
    if product is None:
        return jsonify({"status": "error", "message": "Product not found"}), 404

    if product.stock < quantity:
        return jsonify({"status": "error", "message": "Insufficient stock"}), 400

    # Deduct stock
    product.stock -= quantity

    # Create order with origin defaulting to 'web'
    origin = data.get('origin', 'web')
    order = Order(
        user_id=user.id,
        product_id=product_id,
        quantity=quantity,
        total_price=product.price * quantity,
        origin=origin,
    )
    db.session.add(order)
    db.session.commit()

    # Record rate limit timestamp only on successful order
    record_order_time(user.id)

    return jsonify({"status": "ok", "data": order.to_dict()}), 201


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders. Admin sees all orders; regular users see only their own."""
    user = get_current_user()
    if user is None:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    if user.role == 'admin':
        orders = Order.query.all()
    else:
        orders = Order.query.filter_by(user_id=user.id).all()

    return jsonify({"status": "ok", "data": [o.to_dict() for o in orders]}), 200
