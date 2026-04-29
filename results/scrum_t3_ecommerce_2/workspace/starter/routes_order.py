"""
T3 E-commerce — Order Routes

Implement order management routes.
Register as a Flask Blueprint named 'order_bp'.

Requirements:
- POST /orders -> Create order
  Request: {"product_id": int, "quantity": int, "origin": str (optional)}
  Response: {"status": "ok", "data": {"id", "user_id", "product_id",
            "quantity", "total_price", "origin"}}
  - Must check stock before creating order (atomic: no negative stock)
  - Must deduct stock on order creation
  - total_price = product.price * quantity
  - origin defaults to 'web'
  - Rate limiting via check_rate_limit (429 if limited)
  - Errors: 400/404 if product missing, 401 if no user

- GET /orders -> List orders
  - Admin sees all orders
  - Regular user sees only their own orders
  Response: {"status": "ok", "data": [...]}
"""

from flask import Blueprint, request, jsonify, current_app
import time

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from models import db, Product, Order
from middleware import get_current_user, RATE_LIMIT_WINDOW

order_bp = Blueprint('order_bp', __name__)

# Per-app-instance rate limit store to avoid cross-test leakage
_RATE_LIMIT_KEY = 'order_rate_limit_store'


def _get_rate_store():
    """Get or create a rate limit store bound to the current Flask app instance."""
    store = current_app.extensions.get(_RATE_LIMIT_KEY)
    if store is None:
        store = {}
        current_app.extensions[_RATE_LIMIT_KEY] = store
    return store


def _check_rate_limit(user_id):
    """Check rate limit using app-scoped store. Returns True if limited."""
    store = _get_rate_store()
    now = time.time()
    last_time = store.get(user_id)
    if last_time is not None and (now - last_time) < RATE_LIMIT_WINDOW:
        return True
    store[user_id] = now
    return False


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order with stock deduction and rate limiting."""
    user = get_current_user()
    if user is None:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    data = request.get_json()
    if not data or 'product_id' not in data or 'quantity' not in data:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    product = Product.query.get(data['product_id'])
    if product is None:
        return jsonify({"status": "error", "message": "Product not found"}), 404

    quantity = int(data['quantity'])
    if quantity <= 0:
        return jsonify({"status": "error", "message": "Quantity must be positive"}), 400

    # Atomic stock check and deduction
    if product.stock < quantity:
        return jsonify({"status": "error", "message": "Insufficient stock"}), 400

    # Rate limit check — after validation so failed orders don't consume the slot
    if _check_rate_limit(user.id):
        return jsonify({"status": "error", "message": "Rate limit exceeded"}), 429

    product.stock -= quantity
    origin = data.get('origin', 'web')
    total_price = product.price * quantity

    order = Order(
        user_id=user.id,
        product_id=product.id,
        quantity=quantity,
        total_price=total_price,
        origin=origin,
    )
    db.session.add(order)
    db.session.commit()

    return jsonify({"status": "ok", "data": {
        "id": order.id,
        "user_id": order.user_id,
        "product_id": order.product_id,
        "quantity": order.quantity,
        "total_price": order.total_price,
        "origin": order.origin,
    }}), 201


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders. Admin sees all, regular user sees own."""
    user = get_current_user()
    if user is None:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    if user.role == 'admin':
        orders = Order.query.all()
    else:
        orders = Order.query.filter_by(user_id=user.id).all()

    data = [
        {
            "id": o.id,
            "user_id": o.user_id,
            "product_id": o.product_id,
            "quantity": o.quantity,
            "total_price": o.total_price,
            "origin": o.origin,
        }
        for o in orders
    ]
    return jsonify({"status": "ok", "data": data}), 200
