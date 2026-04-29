"""
T3 E-commerce — Product Routes (Sample 1)

Design choices for this variant:
- Custom @admin_required decorator with functools.wraps for clean separation of concerns
- Dictionary dispatch pattern for error response generation (single _error() helper)
- Dictionary comprehension for product serialization via _serialize helper
- Strict field validation: rejects unknown keys in POST body
- Explicit 401 for missing auth, 403 for wrong role, 400 for bad input
"""

from functools import wraps
from flask import Blueprint, request, jsonify, g

from models import Product
from middleware import get_current_user

product_bp = Blueprint('product_bp', __name__)

# --- Error response helper (dictionary dispatch) ---

_ERROR_TEMPLATES = {
    400: "Bad request: {detail}",
    401: "Authentication required: {detail}",
    403: "Forbidden: {detail}",
    404: "Not found: {detail}",
}


def _error(status_code, detail=""):
    """Build a standardized error JSON response using template dispatch."""
    template = _ERROR_TEMPLATES.get(status_code, "Error: {detail}")
    return jsonify({"status": "error", "message": template.format(detail=detail)}), status_code


# --- Serialization helper ---

_ALLOWED_PRODUCT_KEYS = ("id", "name", "price", "stock")


def _serialize(product):
    """Serialize a Product model instance to a dict using only allowed keys."""
    return {k: getattr(product, k) for k in _ALLOWED_PRODUCT_KEYS}


# --- Auth decorator ---

def admin_required(fn):
    """Decorator that enforces authentication and admin role.

    Returns 401 if no X-User-Id header is present.
    Returns 403 if the user is not an admin.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return _error(401, "X-User-Id header is missing or invalid")
        if user.role != "admin":
            return _error(403, "admin role is required for this operation")
        g.current_user = user
        return fn(*args, **kwargs)
    return wrapper


# --- Routes ---

@product_bp.route("/products", methods=["GET"])
def list_products():
    """Return all products as a JSON array."""
    products = Product.query.all()
    data = [_serialize(p) for p in products]
    return jsonify({"status": "ok", "data": data}), 200


@product_bp.route("/products", methods=["POST"])
@admin_required
def create_product():
    """Create a new product. Admin only.

    Validates that exactly the required fields are present and have
    correct types before inserting into the database.
    """
    body = request.get_json(silent=True)
    if body is None:
        return _error(400, "request body must be valid JSON")

    # Reject unknown keys
    unexpected = set(body.keys()) - {"name", "price", "stock"}
    if unexpected:
        return _error(400, f"unexpected fields: {', '.join(sorted(unexpected))}")

    # Validate presence
    name = body.get("name")
    price = body.get("price")
    stock = body.get("stock")

    if not name or not isinstance(name, str):
        return _error(400, "'name' is required and must be a non-empty string")
    if price is None:
        return _error(400, "'price' is required")
    try:
        price = float(price)
    except (ValueError, TypeError):
        return _error(400, "'price' must be a number")
    if stock is None:
        return _error(400, "'stock' is required")
    try:
        stock = int(stock)
    except (ValueError, TypeError):
        return _error(400, "'stock' must be an integer")

    product = Product(name=name, price=price, stock=stock)
    from app import db
    db.session.add(product)
    db.session.commit()

    return jsonify({"status": "ok", "data": _serialize(product)}), 201
