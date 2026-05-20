"""
ATU-003 Sample 2: Order Routes — Function-Based + Rate Limit Decorator + Origin Support

Design decisions (distinct from Sample 1):
1. **Function-based routes instead of MethodView**: The MethodView pattern from
   ATU-002 was elegant but made it harder to apply per-route decorators (like
   rate limiting) selectively. Function-based routes allow us to decorate only
   POST /orders with @rate_limit while leaving GET /orders untouched. This is
   more Pythonic for "apply middleware to one endpoint" scenarios.
2. **@rate_limit decorator**: A reusable decorator that wraps any order-creation
   route with rate limiting logic. The decorator:
   - Extracts the user from X-User-Id header
   - Checks the rate limit via middleware.check_order_rate_limit()
   - Returns 429 if rate limited, otherwise proceeds to the wrapped function
   - Records successful orders via middleware.record_order_success()
   This separation of concerns means the rate limit logic lives in one place
   and can be applied to any future order-creation endpoint.
3. **Origin field support**: The POST /orders endpoint accepts an optional
   'origin' field in the JSON body, defaulting to 'web'. The origin is
   persisted to the Order model and included in all serialized responses.
4. **Atomic stock deduction preserved**: The existing db.session.execute(update(...))
   pattern with nested transaction (savepoint) is kept unchanged, as it was
   already correct and battle-tested.
5. **Separate InsufficientStockError exception**: Inherited from ATU-002's
   proven pattern for clean error handling with savepoint rollback.
"""

import functools

from flask import Blueprint, request, jsonify
from sqlalchemy import update

from app import db
from middleware import get_current_user, check_order_rate_limit, record_order_success
from models import Order, Product

order_bp = Blueprint('order_bp', __name__)


# ---------------------------------------------------------------------------
# Custom exception for stock-insufficient scenario
# ---------------------------------------------------------------------------

class InsufficientStockError(Exception):
    """Raised when an atomic stock UPDATE affects zero rows."""
    def __init__(self, product_id, requested_qty):
        self.product_id = product_id
        self.requested_qty = requested_qty
        super().__init__(f'Insufficient stock for product {product_id}')


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------

def serialize_order(order):
    """Convert an Order ORM instance into a JSON-serializable dict."""
    return {
        'id': order.id,
        'user_id': order.user_id,
        'product_id': order.product_id,
        'quantity': order.quantity,
        'total_price': float(order.total_price),
        'origin': order.origin,
    }


# ---------------------------------------------------------------------------
# Input validation helper
# ---------------------------------------------------------------------------

def validate_order_payload():
    """
    Validate the incoming JSON body for order creation.

    Returns a tuple (validated_fields_dict, error_response_or_None).
    Extracts product_id, quantity, and the optional origin field.
    """
    data = request.get_json(silent=True)
    if data is None:
        return None, (jsonify({'status': 'error', 'message': 'Request body must be valid JSON'}), 400)

    required = ('product_id', 'quantity')
    missing = [f for f in required if f not in data]
    if missing:
        return None, (jsonify({'status': 'error', 'message': f'Missing required fields: {", ".join(missing)}'}), 400)

    try:
        product_id = int(data['product_id'])
    except (TypeError, ValueError):
        return None, (jsonify({'status': 'error', 'message': 'Field "product_id" must be a valid integer'}), 400)

    try:
        quantity = int(data['quantity'])
        if quantity <= 0:
            return None, (jsonify({'status': 'error', 'message': 'Field "quantity" must be a positive integer'}), 400)
    except (TypeError, ValueError):
        return None, (jsonify({'status': 'error', 'message': 'Field "quantity" must be a valid integer'}), 400)

    # Extract optional origin, default to 'web'
    origin = data.get('origin', 'web')
    if not isinstance(origin, str) or not origin.strip():
        origin = 'web'
    origin = origin.strip()[:20]  # Truncate to match DB column size

    return {'product_id': product_id, 'quantity': quantity, 'origin': origin}, None


# ---------------------------------------------------------------------------
# Rate Limit Decorator
# ---------------------------------------------------------------------------

def rate_limit(view_func):
    """
    Decorator that enforces per-user order rate limiting on a route.

    Flow:
      1. Authenticate the user via X-User-Id header.
      2. Check rate limit via middleware.check_order_rate_limit(user_id).
      3. If rate limited, return HTTP 429 immediately.
      4. Otherwise, call the wrapped view function.
      5. If the view returns a success status (2xx), record the order time
         via middleware.record_order_success(user_id).

    This decorator is designed to wrap the POST /orders route handler.
    Authentication is handled here (before rate limit check) so that
    unauthenticated requests get 401, not 429.
    """
    @functools.wraps(view_func)
    def wrapper(*args, **kwargs):
        # Step 1: Authenticate
        user = get_current_user()
        if user is None:
            return jsonify({
                'status': 'error',
                'message': 'Authentication required: provide a valid X-User-Id header',
            }), 401

        # Step 2: Check rate limit
        if not check_order_rate_limit(user.id):
            return jsonify({
                'status': 'error',
                'message': f'Rate limit exceeded: maximum {10} seconds between orders',
            }), 429

        # Step 3: Call the original view function
        # Inject the authenticated user so the view doesn't need to re-auth.
        response = view_func(user=user, *args, **kwargs)

        # Step 4: Record successful order for rate limiting
        # Check if the response indicates success (2xx status code)
        if isinstance(response, tuple):
            status_code = response[1]
        else:
            status_code = 200

        if 200 <= status_code < 300:
            record_order_success(user.id)

        return response

    return wrapper


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """GET /orders — List orders. Admin sees all, regular user sees own."""
    user = get_current_user()
    if user is None:
        return jsonify({
            'status': 'error',
            'message': 'Authentication required: provide a valid X-User-Id header',
        }), 401

    query = Order.query
    if user.role != 'admin':
        query = query.filter(Order.user_id == user.id)

    orders = query.order_by(Order.id.desc()).all()
    return jsonify({
        'status': 'ok',
        'data': [serialize_order(o) for o in orders],
    })


@order_bp.route('/orders', methods=['POST'])
@rate_limit
def create_order(user):
    """
    POST /orders — Create an order with atomic stock deduction.

    The `user` parameter is injected by the @rate_limit decorator.
    Accepts optional 'origin' field (default: 'web').
    """
    fields, err = validate_order_payload()
    if err:
        return err

    product_id = fields['product_id']
    quantity = fields['quantity']
    origin = fields['origin']

    # Verify product exists before attempting stock deduction
    product = db.session.get(Product, product_id)
    if product is None:
        return jsonify({
            'status': 'error',
            'message': f'Product with id {product_id} not found',
        }), 404

    total_price = round(product.price * quantity, 2)

    # Use a nested transaction (savepoint) so that if order creation fails
    # after stock deduction, the stock is automatically rolled back.
    try:
        with db.session.begin_nested():
            # Atomic stock deduction via UPDATE with WHERE guard.
            # This single statement both checks and decrements stock,
            # avoiding the TOCTOU race of separate SELECT + UPDATE.
            stmt = (
                update(Product.__table__)
                .where(Product.id == product_id, Product.stock >= quantity)
                .values(stock=Product.stock - quantity)
            )
            result = db.session.execute(stmt)

            if result.rowcount == 0:
                raise InsufficientStockError(product_id, quantity)

            order = Order(
                user_id=user.id,
                product_id=product_id,
                quantity=quantity,
                total_price=total_price,
                origin=origin,
            )
            db.session.add(order)

        # Commit the outer transaction (includes the savepoint).
        db.session.commit()

    except InsufficientStockError:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'Insufficient stock for product {product_id}. Requested {quantity}, available {product.stock}',
        }), 400

    except Exception:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': 'Internal server error while creating order',
        }), 500

    return jsonify({
        'status': 'ok',
        'data': serialize_order(order),
    }), 201
