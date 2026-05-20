"""
T3 E-commerce -- Order Routes

Implement order management routes.
Register as a Flask Blueprint named 'order_bp'.

Requirements:
- POST /orders -> Create order
  Request: {"product_id": int, "quantity": int, "origin": str (optional)}
  Response: {"status": "ok", "data": {"id": int, "user_id": int, "product_id": int,
            "quantity": int, "total_price": float, "origin": str}}
  - Must check stock before creating order
  - Must deduct stock on order creation (atomic, concurrency-safe)
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

from models import db, Order, Product
import middleware

order_bp = Blueprint('order_bp', __name__)


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order with atomic stock deduction."""
    # --- Authentication ---
    user = middleware.get_current_user()
    if user is None:
        return jsonify({'status': 'error', 'message': 'Authentication required'}), 401

    # --- Rate limiting ---
    if not middleware.check_rate_limit(user.id):
        return jsonify({'status': 'error', 'message': 'Too Many Requests'}), 429

    # --- Parse request ---
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'Invalid request body'}), 400

    product_id = data.get('product_id')
    quantity = data.get('quantity')
    origin = data.get('origin', 'web')

    if product_id is None or quantity is None:
        return jsonify({'status': 'error', 'message': 'product_id and quantity are required'}), 400

    try:
        product_id = int(product_id)
        quantity = int(quantity)
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'message': 'product_id and quantity must be integers'}), 400

    if quantity <= 0:
        return jsonify({'status': 'error', 'message': 'quantity must be positive'}), 400

    # --- Check product exists ---
    product = Product.query.get(product_id)
    if product is None:
        return jsonify({'status': 'error', 'message': 'Product not found'}), 404

    # --- Atomic stock deduction using SELECT FOR UPDATE ---
    try:
        # Lock the product row to prevent concurrent modifications
        locked_product = db.session.execute(
            db.select(Product).where(Product.id == product_id).with_for_update()
        ).scalar_one()

        if locked_product.stock < quantity:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': 'Insufficient stock'})

        # Deduct stock
        locked_product.stock -= quantity

        # Create order
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

    except Exception:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders. Admin sees all, regular user sees only their own."""
    # --- Authentication ---
    user = middleware.get_current_user()
    if user is None:
        return jsonify({'status': 'error', 'message': 'Authentication required'}), 401

    # --- Query based on role ---
    if user.role == 'admin':
        orders = Order.query.all()
    else:
        orders = Order.query.filter_by(user_id=user.id).all()

    return jsonify({
        'status': 'ok',
        'data': [
            {
                'id': o.id,
                'user_id': o.user_id,
                'product_id': o.product_id,
                'quantity': o.quantity,
                'total_price': o.total_price,
                'origin': o.origin,
            }
            for o in orders
        ],
    }), 200
