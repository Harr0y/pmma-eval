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
  - Must deduct stock on order creation (atomic via SELECT FOR UPDATE)
  - total_price = product.price * quantity
  - Errors: 400/404 if invalid product, 401 if no user

- GET /orders -> List orders
  - Admin sees all orders
  - Regular user sees only their own orders
  Response: {"status": "ok", "data": [...]}

Use middleware.get_current_user() to get the authenticated user.
"""

from flask import Blueprint, request, jsonify
from sqlalchemy import select
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from middleware import get_current_user, check_rate_limit
from models import Product, Order, db

order_bp = Blueprint('order_bp', __name__)


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order with atomic stock deduction."""
    user = get_current_user()
    if not user:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    allowed, status_code = check_rate_limit(user.id)
    if not allowed:
        return jsonify({"status": "error", "message": "Rate limit exceeded"}), status_code

    body = request.get_json(silent=True)
    if not body:
        return jsonify({"status": "error", "message": "Invalid request body"}), 400

    product_id = body.get('product_id')
    quantity = body.get('quantity')
    origin = body.get('origin', 'web')

    if product_id is None or quantity is None:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    # Atomic stock deduction using SELECT FOR UPDATE
    product = db.session.execute(
        select(Product).where(Product.id == product_id).with_for_update()
    ).scalar_one_or_none()

    if not product:
        return jsonify({"status": "error", "message": "Product not found"}), 404

    if product.stock < quantity:
        return jsonify({"status": "error", "message": "Insufficient stock"}), 400

    # Deduct stock atomically (row is still locked by FOR UPDATE)
    product.stock -= quantity

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
    """List orders. Admin sees all, regular users see only their own."""
    user = get_current_user()
    if not user:
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
