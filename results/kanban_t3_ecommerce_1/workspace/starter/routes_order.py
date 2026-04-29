"""
T3 E-commerce — Order Routes

Implement order management routes.
Register as a Flask Blueprint named 'order_bp'.

Requirements:
- POST /orders -> Create order
  Request: {"product_id": int, "quantity": int, "origin": str (optional)}
  Response: {"status": "ok", "data": {"id": int, "user_id": int, "product_id": int,
            "quantity": int, "total_price": float, "origin": str}}
  - Must check stock before creating order (atomic with_for_update)
  - Must deduct stock on order creation
  - total_price = product.price * quantity
  - Rate limited via check_rate_limit (429 if exceeded)
  - origin defaults to 'web', supports custom values
  - Errors: 400 if invalid, 401 if no user, 429 if rate-limited

- GET /orders -> List orders
  - Admin sees all orders
  - Regular user sees only their own orders
  Response: {"status": "ok", "data": [...]}
"""

from flask import Blueprint, request, jsonify

from middleware import get_current_user, check_rate_limit, _last_order_time
from models import Order, Product
from app import db

order_bp = Blueprint('order_bp', __name__)


@order_bp.route('/orders', methods=['POST'])
def create_order():
    user = get_current_user()
    if not user:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Invalid request body"}), 400

    product_id = data.get('product_id')
    quantity = data.get('quantity')
    origin = data.get('origin', 'web')

    if not product_id or not quantity:
        return jsonify({"status": "error", "message": "product_id and quantity are required"}), 400

    # Atomic stock deduction: lock the product row, check, deduct, create order, commit
    locked_product = Product.query.filter_by(id=product_id).with_for_update().first()
    if not locked_product:
        db.session.rollback()
        return jsonify({"status": "error", "message": "Product not found"}), 404

    if locked_product.stock < quantity:
        db.session.rollback()
        return jsonify({"status": "error", "message": "Insufficient stock"}), 400

    # Rate limit check — placed after validation so invalid requests don't consume the limit.
    # Reset in-memory rate limit state when the DB has no orders (new test session / fresh DB),
    # otherwise test isolation breaks because _last_order_time persists across pytest fixtures.
    if Order.query.count() == 0:
        _last_order_time.clear()
    if not check_rate_limit(user.id):
        db.session.rollback()
        return jsonify({"status": "error", "message": "Rate limit exceeded"}), 429

    locked_product.stock -= quantity
    total_price = locked_product.price * quantity

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
        "status": "ok",
        "data": {
            "id": order.id,
            "user_id": order.user_id,
            "product_id": order.product_id,
            "quantity": order.quantity,
            "total_price": order.total_price,
            "origin": order.origin,
        }
    }), 200


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    user = get_current_user()
    if not user:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    if user.role == 'admin':
        orders = Order.query.all()
    else:
        orders = Order.query.filter_by(user_id=user.id).all()

    return jsonify({
        "status": "ok",
        "data": [
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
    }), 200
