"""
T3 E-commerce -- Order Routes (Sample 1: Sliding-Window Rate Limiter)

Mutation Strategy: This variant integrates the SlidingWindowRateLimiter from
middleware_sample1 into the create_order flow.  The rate-limit check is
placed *after* authentication but *before* any business logic (payload
parsing, stock deduction, etc.), ensuring that:

  1. Unauthenticated requests are rejected with 401 (not 429).
  2. Rate-limited users receive a clear 429 response with a JSON body.
  3. All existing behaviour (origin coercion, atomic stock deduction,
     total_price calculation, admin/user filtering on list) is preserved.

The guard-clause + early-return control flow from the ATU evolutionary
heritage is maintained throughout.
"""

from flask import Blueprint, request, jsonify
from sqlalchemy import text

from models import Product, Order, db
from middleware import get_current_user, check_rate_limit

order_bp = Blueprint('order_bp', __name__)

# ---- Tiny helpers ----

_ORIGIN_DEFAULT = 'web'


def _fail(message, status=400):
    """Return a standardized error response tuple."""
    return jsonify({'status': 'error', 'message': message}), status


def _coerce_origin(raw):
    """Return a validated origin string.

    If *raw* is a non-empty string, return it stripped.
    Otherwise return the default 'web'.  This prevents accidental storage
    of non-string types (int, None, list, etc.) that a naive
    ``body.get('origin', 'web')`` would happily persist.
    """
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return _ORIGIN_DEFAULT


def _serialize_order(o):
    """Convert an Order ORM object to a plain dict for JSON responses."""
    return {
        'id': o.id,
        'user_id': o.user_id,
        'product_id': o.product_id,
        'quantity': o.quantity,
        'total_price': o.total_price,
        'origin': o.origin,
    }


# ---- Routes ----

@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create an order after validating auth, rate limit, payload, product, and stock."""

    # --- Auth guard ---
    user = get_current_user()
    if user is None:
        return _fail('Authentication required: provide a valid X-User-Id header', 401)

    # --- Rate-limit guard (sliding window, per user_id) ---
    if not check_rate_limit(user.id):
        return _fail('Rate limit exceeded: please wait before placing another order', 429)

    # --- Payload guard ---
    body = request.get_json(silent=True)
    if not body or not isinstance(body, dict):
        return _fail('Request body must be a JSON object')

    try:
        product_id = int(body['product_id'])
    except (KeyError, TypeError, ValueError):
        return _fail('Invalid or missing "product_id"')

    try:
        quantity = int(body['quantity'])
        if quantity <= 0:
            return _fail('Quantity must be a positive integer')
    except (KeyError, TypeError, ValueError):
        return _fail('Invalid or missing "quantity"')

    # --- Origin extraction (coerced, not raw) ---
    origin = _coerce_origin(body.get('origin'))

    # --- Product existence guard ---
    product = Product.query.get(product_id)
    if product is None:
        return _fail(f'Product {product_id} not found', 404)

    # --- Stock guard + atomic deduction ---
    # Use a single UPDATE ... WHERE to atomically check and decrement stock.
    # If stock < quantity, zero rows are affected and we reject the order.
    # This avoids the race condition of a separate SELECT then UPDATE.
    result = db.session.execute(
        text('UPDATE product SET stock = stock - :qty WHERE id = :pid AND stock >= :qty'),
        {'qty': quantity, 'pid': product_id},
    )
    db.session.commit()

    if result.rowcount == 0:
        return _fail('Insufficient stock')

    # Re-read the product to get the new stock (not strictly needed here,
    # but keeps data consistent if we wanted to return stock in the response).
    product = Product.query.get(product_id)

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
        'data': _serialize_order(order),
    }), 201


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders: admin sees all, regular user sees only their own."""

    user = get_current_user()
    if user is None:
        return _fail('Authentication required: provide a valid X-User-Id header', 401)

    if user.role == 'admin':
        orders = Order.query.order_by(Order.id).all()
    else:
        orders = Order.query.filter_by(user_id=user.id).order_by(Order.id).all()

    return jsonify({
        'status': 'ok',
        'data': [_serialize_order(o) for o in orders],
    })
