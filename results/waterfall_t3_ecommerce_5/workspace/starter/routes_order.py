"""
T3 E-commerce — Order Routes

Implement order management routes.
Register as a Flask Blueprint named 'order_bp'.

Requirements:
- POST /orders -> Create order
  Request: {"product_id": int, "quantity": int, "origin": str (optional)}
  Response: {"status": "ok", "data": {"id": int, "user_id": int, "product_id": int,
            "quantity": int, "total_price": float, "origin": str}}
  - Must check stock before creating order (atomic conditional UPDATE)
  - Must deduct stock on order creation
  - total_price = product.price * quantity
  - Rate limiting: same user can only place 1 order per 10 seconds
  - Errors: 400 if invalid, 401 if no user, 404 if product not found,
            429 if rate limited

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

from middleware import get_current_user, check_rate_limit, mark_order_placed
from models import Order, Product
from app import db

order_bp = Blueprint('order_bp', __name__)


def _serialize_order(order):
    """Serialize an Order object to a dictionary (design.md §3.4)."""
    return {
        'id': order.id,
        'user_id': order.user_id,
        'product_id': order.product_id,
        'quantity': order.quantity,
        'total_price': order.total_price,
        'origin': order.origin
    }


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order (design.md §2.3).

    Steps:
    1. Authenticate user via get_current_user() -> 401 if None
    2. Rate limit check via check_rate_limit(user.id) -> 429 if limited
    3. Validate request params: product_id (positive int), quantity (positive int > 0),
       origin (optional, default 'web') -> 400 if invalid
    4. Atomic stock deduction via conditional UPDATE (design.md §3.2)
    5. Calculate total_price, create Order record, commit
    6. Call mark_order_placed(user.id) only after successful commit
    7. Return order data (201)
    """
    # Step 1: Authenticate user
    user = get_current_user()
    if user is None:
        return {"status": "error", "message": "Authentication required"}, 401

    # Step 2: Rate limit check
    if check_rate_limit(user.id):
        return {"status": "error", "message": "Rate limit exceeded"}, 429

    # Step 3: Validate request parameters
    data = request.get_json(silent=True)
    if data is None:
        return {"status": "error", "message": "Request body must be JSON"}, 400

    # Validate product_id: must be a positive integer
    product_id = data.get('product_id')
    if product_id is None:
        return {"status": "error", "message": "product_id is required"}, 400
    if not isinstance(product_id, int) or isinstance(product_id, bool) or product_id <= 0:
        return {"status": "error", "message": "product_id must be a positive integer"}, 400

    # Validate quantity: must be a positive integer (> 0)
    quantity = data.get('quantity')
    if quantity is None:
        return {"status": "error", "message": "quantity is required"}, 400
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        return {"status": "error", "message": "quantity must be a positive integer"}, 400

    # Validate origin: optional, default 'web'
    origin = data.get('origin', 'web')

    # Steps 4-5: Atomic stock deduction (design.md §3.2) using conditional UPDATE
    result = db.session.execute(
        update(Product)
        .where(Product.id == product_id, Product.stock >= quantity)
        .values(stock=Product.stock - quantity)
    )

    if result.rowcount == 0:
        # Check whether product doesn't exist or stock is insufficient
        product = Product.query.get(product_id)
        if product is None:
            return {"status": "error", "message": "Product not found"}, 404
        else:
            return {"status": "error", "message": "Insufficient stock"}, 400

    # Fetch the product for price calculation (product exists since UPDATE succeeded)
    product = Product.query.get(product_id)

    # Step 6: Calculate total_price and create Order
    total_price = product.price * quantity
    order = Order(
        user_id=user.id,
        product_id=product_id,
        quantity=quantity,
        total_price=total_price,
        origin=origin
    )
    db.session.add(order)
    db.session.commit()

    # Step 7: Only mark rate limit AFTER successful commit
    mark_order_placed(user.id)

    return {"status": "ok", "data": _serialize_order(order)}, 201


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders (design.md §2.4).

    Steps:
    1. Authenticate user via get_current_user() -> 401 if None
    2. Admin -> Order.query.all()
    3. Regular user -> Order.query.filter_by(user_id=user.id).all()
    4. Serialize and return
    """
    # Step 1: Authenticate user
    user = get_current_user()
    if user is None:
        return {"status": "error", "message": "Authentication required"}, 401

    # Step 2-3: Role-based filtering
    if user.role == 'admin':
        orders = Order.query.all()
    else:
        orders = Order.query.filter_by(user_id=user.id).all()

    # Step 4: Serialize and return
    return {"status": "ok", "data": [_serialize_order(o) for o in orders]}, 200
