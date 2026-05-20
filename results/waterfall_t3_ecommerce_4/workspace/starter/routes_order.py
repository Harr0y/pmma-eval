"""
T3 E-commerce — Order Routes

Implement order management routes.
Register as a Flask Blueprint named 'order_bp'.

Requirements:
- POST /orders -> Create order
  Request: {"product_id": int, "quantity": int, "origin": str (optional, default "web")}
  Response: {"status": "ok", "data": {"id": int, "user_id": int, "product_id": int,
            "quantity": int, "total_price": float, "origin": str}}
  - Must check stock before creating order
  - Must deduct stock on order creation (atomic UPDATE ... WHERE stock >= quantity)
  - total_price = product.price * quantity
  - Errors: 400 if invalid, 401 if no user, 429 if rate limited

- GET /orders -> List orders
  - Admin sees all orders
  - Regular user sees only their own orders
  Response: {"status": "ok", "data": [{"id": int, "user_id": int, "product_id": int,
            "quantity": int, "total_price": float, "origin": str}, ...]}

Use middleware.get_current_user() to get the authenticated user.
"""

from flask import Blueprint, request, jsonify
from middleware import get_current_user, check_rate_limit, update_rate_limit
from models import Product, Order
from app import db

order_bp = Blueprint('order_bp', __name__)


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order. Authenticated users only."""
    # Step 1: Get current user
    user = get_current_user()

    # Step 2: Check authentication
    if user is None:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    # Step 3: Check rate limit (read-only check, does NOT update timestamp)
    if not check_rate_limit(user.id):
        # Step 4: Rate limit exceeded
        return jsonify({"status": "error", "message": "Rate limit exceeded"}), 429

    # Step 5: Validate request body
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"status": "error", "message": "Request body must be JSON"}), 400

    product_id = body.get('product_id')
    quantity = body.get('quantity')

    if product_id is None or quantity is None:
        return jsonify({"status": "error", "message": "Missing required fields: product_id, quantity"}), 400

    # Validate quantity is a positive integer
    try:
        quantity = int(quantity)
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "quantity must be a positive integer"}), 400

    if quantity <= 0:
        return jsonify({"status": "error", "message": "quantity must be a positive integer"}), 400

    try:
        product_id = int(product_id)
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "product_id must be an integer"}), 400

    # Step 6: Query product
    product = Product.query.get(product_id)
    if product is None:
        return jsonify({"status": "error", "message": "Product not found"}), 404

    # Step 9: Atomic stock deduction using UPDATE ... WHERE stock >= quantity
    # This prevents concurrent overselling in SQLite (no row-level locks)
    result = db.session.execute(
        db.text("UPDATE product SET stock = stock - :qty WHERE id = :pid AND stock >= :qty"),
        {"qty": quantity, "pid": product_id}
    )

    # Step 9 (continued): Check affected rows
    if result.rowcount == 0:
        # Stock insufficient due to either initial check or concurrent race
        return jsonify({"status": "error", "message": "Insufficient stock"}), 400

    # Step 10: Create order with calculated total_price
    total_price = product.price * quantity
    origin = request.json.get('origin', 'web')

    order = Order(
        user_id=user.id,
        product_id=product_id,
        quantity=quantity,
        total_price=total_price,
        origin=origin
    )
    db.session.add(order)

    # Step 12: Commit transaction
    db.session.commit()

    # Step 13: Update rate limit timestamp ONLY after successful order creation
    update_rate_limit(user.id)

    # Step 14: Return 201 with order data including origin
    return jsonify({
        "status": "ok",
        "data": {
            "id": order.id,
            "user_id": order.user_id,
            "product_id": order.product_id,
            "quantity": order.quantity,
            "total_price": order.total_price,
            "origin": order.origin
        }
    }), 201


@order_bp.route('/orders', methods=['GET'])
def get_orders():
    """List orders. Admin sees all, regular user sees their own."""
    # Step 1: Get current user
    user = get_current_user()

    # Step 2: Check authentication
    if user is None:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    # Step 3 & 4: Filter by role
    if user.role == 'admin':
        orders = Order.query.all()
    else:
        orders = Order.query.filter_by(user_id=user.id).all()

    # Step 5: Serialize with origin field
    data = [
        {
            "id": o.id,
            "user_id": o.user_id,
            "product_id": o.product_id,
            "quantity": o.quantity,
            "total_price": o.total_price,
            "origin": o.origin
        }
        for o in orders
    ]

    # Step 6: Return 200 with order list
    return jsonify({"status": "ok", "data": data}), 200
