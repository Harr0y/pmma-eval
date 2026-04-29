"""
T3 E-commerce — Order Routes

Implement order management routes.
Register as a Flask Blueprint named 'order_bp'.

Requirements:
- POST /orders -> Create order
  Request: {"product_id": int, "quantity": int, "origin": str(optional)}
  Response: {"status": "ok", "data": {"id", "user_id", "product_id",
            "quantity", "total_price", "origin"}}
  - Authenticate via X-User-Id header
  - Rate limit: check_rate_limit(user_id) -> 429 if exceeded
  - Must check stock before creating order (with_for_update atomic lock)
  - Must deduct stock on order creation
  - total_price = product.price * quantity
  - origin defaults to 'web' if not provided
  - record_order_success(user_id) after successful commit
  - Errors: 400 if invalid/insufficient stock, 401 if no user, 404 if product not found, 429 if rate limited

- GET /orders -> List orders
  - Authenticate via X-User-Id header
  - Admin sees all orders
  - Regular user sees only their own orders
  Response: {"status": "ok", "data": [...]}

Use middleware.get_current_user() to get the authenticated user.
Use middleware.check_rate_limit() and middleware.record_order_success() for rate limiting.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from flask import Blueprint, request, jsonify
from models import Product, Order
from middleware import get_current_user, check_rate_limit, record_order_success
from app import db

order_bp = Blueprint('order_bp', __name__)


def order_to_dict(o):
    """Serialize an Order object to a dictionary.

    design.md Section 4.3 — includes origin field.
    """
    return {
        'id': o.id,
        'user_id': o.user_id,
        'product_id': o.product_id,
        'quantity': o.quantity,
        'total_price': o.total_price,
        'origin': o.origin,
    }


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order.

    design.md Section 3.3 / FR-003-1..5, FR-004-1..4, FR-005-1..3, FR-006-1..4

    Flow:
    1. Authenticate via X-User-Id header -> 401 if missing/invalid
    2. Check rate limit -> 429 if exceeded
    3. Parse and validate request body (product_id, quantity, origin optional)
    4. Validate product exists -> 404 if not found
    5. Atomic stock deduction with with_for_update() -> 400 if insufficient
    6. Create Order, commit transaction
    7. Record rate limit success timestamp (after commit)
    8. Return 201 with order data including origin
    """
    # Step 1: Authentication (design.md Section 3.3, FR-001-2, FR-001-4)
    user = get_current_user()
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    # Step 2: Rate limiting (design.md Section 4.2, FR-005-1)
    if not check_rate_limit(user.id):
        return jsonify({'status': 'error', 'message': 'Rate limit exceeded'}), 429

    # Step 3: Parse request body (design.md Section 3.3, FR-003-2, FR-004-2)
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    product_id = data.get('product_id')
    quantity = data.get('quantity')
    origin = data.get('origin', 'web')  # FR-004-3: default 'web'

    # Validate required fields
    if product_id is None or quantity is None:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    # Validate types and values (design.md Section 7: implicit requirements)
    try:
        product_id = int(product_id)
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    if quantity < 1:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    # Step 4: Validate product exists (design.md Section 3.3, FR-003-9)
    # Step 5: Atomic stock deduction (design.md Section 4.1, FR-006-1..4)
    product = Product.query.filter_by(id=product_id).with_for_update().first()
    if not product:
        return jsonify({'status': 'error', 'message': 'Product not found'}), 404

    # Check stock sufficiency (FR-003-4, FR-006-2, FR-006-3, FR-006-4)
    if product.stock < quantity:
        return jsonify({'status': 'error', 'message': 'Insufficient stock'}), 400

    # Step 6: Deduct stock and create order (FR-003-3, FR-003-5)
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

    # Step 7: Record rate limit success AFTER commit (design.md Section 4.2, FR-005-1)
    record_order_success(user.id)

    # Step 8: Return 201 with order data (design.md Section 3.3, FR-004-4)
    return jsonify({
        'status': 'ok',
        'data': order_to_dict(order),
    }), 201


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders. Admin sees all, regular user sees only their own.

    design.md Section 3.4 / FR-003-6..8, FR-004-4

    Flow:
    1. Authenticate via X-User-Id header -> 401 if missing/invalid
    2. Admin -> query all orders
    3. Regular user -> query orders filtered by user_id
    4. Serialize and return (including origin field)
    """
    # Step 1: Authentication (design.md Section 3.4, FR-001-2, FR-001-4)
    user = get_current_user()
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    # Step 2 & 3: Query based on role (design.md Section 3.4, FR-003-7, FR-003-8)
    if user.role == 'admin':
        orders = Order.query.all()
    else:
        orders = Order.query.filter_by(user_id=user.id).all()

    # Step 4: Serialize and return (design.md Section 3.4, FR-004-4)
    data = [order_to_dict(o) for o in orders]
    return jsonify({'status': 'ok', 'data': data})
