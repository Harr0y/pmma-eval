"""
T3 Ecommerce - Order Routes (Sample 3)

Inherited traits:
- Atomic stock deduction via conditional UPDATE:
  UPDATE product SET stock = stock - :qty WHERE id = :pid AND stock >= :qty
  rowcount == 0 means insufficient stock.
- Two-phase rate limiting: check before processing, mark only after commit.
- Order model includes 'origin' field with default 'web'.
- Service layer pattern: create_order_service() in middleware.py handles
  business logic, routes only handle HTTP layer.
- Tuple return pattern: (result, error_response) for composable error handling.

Key fix from Gen 1:
- Rate limit state lives on the Flask app object (via middleware_sample3),
  so it resets between pytest fixtures but persists within a single test.

Cross-inherited traits:
- Dedicated _serialize helper for ORM-to-dict conversion.
- Validation-first flow: auth check -> input validation -> DB operations.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Blueprint, request, jsonify
from sqlalchemy import text
from app import db
from models import Product, Order
from middleware import get_current_user, check_rate_limit, mark_rate_limit_success

order_bp = Blueprint('order_bp', __name__)


def _serialize(order):
    """Convert an Order ORM object to a plain dict."""
    return {
        'id': order.id,
        'user_id': order.user_id,
        'product_id': order.product_id,
        'quantity': order.quantity,
        'total_price': order.total_price,
        'origin': order.origin,
    }


@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order.

    Request: {"product_id": int, "quantity": int, "origin": str (optional)}
    Response: {"status": "ok", "data": {...}}
    Errors: 401 (no auth), 429 (rate limited), 400 (invalid input / no stock)
    """
    # Phase 1: Authentication
    user, error = get_current_user()
    if error:
        return error

    # Phase 2: Rate limiting check (before any DB work)
    if check_rate_limit(user.id):
        return jsonify({'status': 'error', 'message': 'Rate limit exceeded'}), 429

    # Phase 3: Input validation
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({'status': 'error', 'message': 'Invalid JSON'}), 400

    product_id = body.get('product_id')
    quantity = body.get('quantity')
    origin = body.get('origin', 'web')

    if not isinstance(product_id, int) or product_id is None:
        return jsonify({'status': 'error', 'message': 'product_id is required'}), 400
    if not isinstance(quantity, int) or quantity is None or quantity <= 0:
        return jsonify({'status': 'error', 'message': 'quantity must be a positive integer'}), 400

    # Phase 4: Validate product exists
    product = Product.query.get(product_id)
    if product is None:
        return jsonify({'status': 'error', 'message': 'Product not found'}), 404

    # Phase 5: Atomic stock deduction via conditional UPDATE
    total_price = product.price * quantity
    result = db.session.execute(
        text('UPDATE product SET stock = stock - :qty WHERE id = :pid AND stock >= :qty'),
        {'qty': quantity, 'pid': product_id}
    )
    if result.rowcount == 0:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'Insufficient stock'}), 400

    # Phase 6: Create order
    order = Order(
        user_id=user.id,
        product_id=product_id,
        quantity=quantity,
        total_price=total_price,
        origin=origin,
    )
    db.session.add(order)
    db.session.commit()

    # Phase 7: Mark rate limit success only after successful commit
    mark_rate_limit_success(user.id)

    return jsonify({'status': 'ok', 'data': _serialize(order)}), 201


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders. Admin sees all, regular user sees own orders only."""
    user, error = get_current_user()
    if error:
        return error

    if user.role == 'admin':
        orders = Order.query.all()
    else:
        orders = Order.query.filter_by(user_id=user.id).all()

    return jsonify({'status': 'ok', 'data': [_serialize(o) for o in orders]})
