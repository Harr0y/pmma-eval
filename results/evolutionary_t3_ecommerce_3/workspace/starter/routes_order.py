"""
T3 E-commerce — Order Routes (Sample 3)

Evolutionary variant combining best-of-breed traits:

1. Atomic stock deduction via raw SQL:
   UPDATE product SET stock = stock - :qty WHERE id = :pid AND stock >= :qty
   Single statement performs check + deduction with no race window.

2. check/record separated rate limiting:
   - check_rate_limit() before order processing (read-only)
   - record_successful_order() after db.session.commit() (write)

3. Whitelist serialization via _ALLOWED_ORDER_KEYS + getattr dict comprehension.

4. _ERROR_TEMPLATES dictionary dispatch for uniform error responses.

5. Rate limiter state stored in current_app.extensions (not module-level dict)
   so it resets automatically when create_app() is called in test fixtures.
"""

from flask import Blueprint, request, jsonify
from sqlalchemy import text

from models import Product, Order
from middleware import get_current_user, check_rate_limit, record_successful_order

order_bp = Blueprint('order_bp', __name__)

# --- Error response helper (dictionary dispatch) ---

_ERROR_TEMPLATES = {
    400: "Bad request: {detail}",
    401: "Authentication required: {detail}",
    403: "Forbidden: {detail}",
    404: "Not found: {detail}",
    429: "Too many requests: {detail}",
}


def _error(status_code, detail=""):
    """Build a standardized error JSON response using template dispatch."""
    template = _ERROR_TEMPLATES.get(status_code, "Error: {detail}")
    return jsonify({"status": "error", "message": template.format(detail=detail)}), status_code


# --- Serialization helper ---

_ALLOWED_ORDER_KEYS = ("id", "user_id", "product_id", "quantity", "total_price", "origin")


def _serialize(order):
    """Serialize an Order model instance to a dict using only allowed keys."""
    return {k: getattr(order, k) for k in _ALLOWED_ORDER_KEYS}


# --- Routes ---

@order_bp.route("/orders", methods=["POST"])
def create_order():
    """Create a new order.

    Steps:
    1. Authenticate user via X-User-Id header.
    2. Check rate limit (read-only, does not consume quota).
    3. Validate request body (product_id, quantity, optional origin).
    4. Atomically deduct stock via raw SQL (single UPDATE with WHERE guard).
    5. Create Order record, commit, then record rate limit timestamp.
    """
    # --- Authentication ---
    user = get_current_user()
    if user is None:
        return _error(401, "X-User-Id header is missing or invalid")

    # --- Rate limit check (read-only) ---
    if check_rate_limit(user.id):
        return _error(429, "order rate limit exceeded (1 order per 10 seconds)")

    # --- Validate request body ---
    body = request.get_json(silent=True)
    if body is None:
        return _error(400, "request body must be valid JSON")

    product_id = body.get("product_id")
    quantity = body.get("quantity")
    origin = body.get("origin", "web")

    if product_id is None:
        return _error(400, "'product_id' is required")
    if quantity is None:
        return _error(400, "'quantity' is required")
    try:
        quantity = int(quantity)
    except (ValueError, TypeError):
        return _error(400, "'quantity' must be an integer")
    if quantity <= 0:
        return _error(400, "'quantity' must be a positive integer")

    # --- Look up product ---
    product = Product.query.get(product_id)
    if product is None:
        return _error(404, "product not found")

    # --- Atomic stock deduction via raw SQL ---
    from app import db
    result = db.session.execute(
        text("UPDATE product SET stock = stock - :qty WHERE id = :pid AND stock >= :qty"),
        {"qty": quantity, "pid": product_id},
    )
    rows_affected = result.rowcount
    # Flush so the updated stock is visible in this transaction
    db.session.flush()

    if rows_affected == 0:
        # Either product disappeared or insufficient stock
        db.session.rollback()
        return _error(400, "insufficient stock")

    # --- Calculate total and create order ---
    total_price = product.price * quantity
    order = Order(
        user_id=user.id,
        product_id=product_id,
        quantity=quantity,
        total_price=total_price,
        origin=str(origin),
    )
    db.session.add(order)
    db.session.commit()

    # --- Record rate limit AFTER successful commit ---
    record_successful_order(user.id)

    return jsonify({"status": "ok", "data": _serialize(order)}), 201


@order_bp.route("/orders", methods=["GET"])
def list_orders():
    """List orders. Admin sees all; regular users see only their own."""
    user = get_current_user()
    if user is None:
        return _error(401, "X-User-Id header is missing or invalid")

    if user.role == "admin":
        orders = Order.query.all()
    else:
        orders = Order.query.filter_by(user_id=user.id).all()

    return jsonify({"status": "ok", "data": [_serialize(o) for o in orders]}), 200
