"""
ATU-001 Sample 2: Product Routes — Decorator-Based Auth + Serializer Helper

Design decisions (distinct from Sample 1):
1. **Decorator-based authorization**: A reusable `admin_required` decorator
   wraps route functions, cleanly separating auth logic from business logic.
2. **Dedicated serializer function**: `serialize_product` converts a Product
   model instance to a plain dict, used consistently in both list and create.
3. **Unified error response helper**: `error_response()` ensures all error
   payloads share the same `{"status": "error", "message": ...}` shape.
4. **Validation helper**: `extract_product_fields` validates and extracts
   required fields from request JSON, centralizing input validation.
"""

import functools
from flask import Blueprint, request, jsonify

from app import db
from middleware import get_current_user
from models import Product

product_bp = Blueprint('product_bp', __name__)


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------

def serialize_product(product):
    """Convert a Product ORM instance into a JSON-serializable dict."""
    return {
        'id': product.id,
        'name': product.name,
        'price': float(product.price),
        'stock': int(product.stock),
    }


# ---------------------------------------------------------------------------
# Unified error helper
# ---------------------------------------------------------------------------

def error_response(status_code, message):
    """Return a JSON error response with a consistent envelope."""
    body = {'status': 'error', 'message': message}
    return jsonify(body), status_code


# ---------------------------------------------------------------------------
# Authorization decorator
# ---------------------------------------------------------------------------

def admin_required(view_func):
    """
    Decorator that enforces admin-only access.

    Flow:
      1. Call get_current_user() — reads X-User-Id header.
      2. If no user (missing/invalid header) -> 401.
      3. If user is not admin -> 403.
      4. Otherwise, proceed with the original view, injecting the user.
    """
    @functools.wraps(view_func)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return error_response(401, 'Authentication required: provide a valid X-User-Id header')
        if user.role != 'admin':
            return error_response(403, 'Forbidden: admin access required')
        return view_func(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Input validation helper
# ---------------------------------------------------------------------------

def extract_product_fields():
    """
    Pull and validate required fields from the request JSON body.

    Returns a tuple (fields_dict, error_response_or_None).
    On success, error_response_or_None is None.
    On failure, error_response_or_None is a Flask response tuple.
    """
    data = request.get_json(silent=True)
    if data is None:
        return None, error_response(400, 'Request body must be valid JSON')

    required = ('name', 'price', 'stock')
    missing = [f for f in required if f not in data]
    if missing:
        return None, error_response(400, f'Missing required fields: {", ".join(missing)}')

    name = data['name']
    if not isinstance(name, str) or not name.strip():
        return None, error_response(400, 'Field "name" must be a non-empty string')

    try:
        price = float(data['price'])
        if price < 0:
            return None, error_response(400, 'Field "price" must be a non-negative number')
    except (TypeError, ValueError):
        return None, error_response(400, 'Field "price" must be a valid number')

    try:
        stock = int(data['stock'])
        if stock < 0:
            return None, error_response(400, 'Field "stock" must be a non-negative integer')
    except (TypeError, ValueError):
        return None, error_response(400, 'Field "stock" must be a valid integer')

    return {'name': name.strip(), 'price': price, 'stock': stock}, None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@product_bp.route('/products', methods=['GET'])
def list_products():
    """GET /products — List all products. No authentication required."""
    products = Product.query.all()
    return jsonify({
        'status': 'ok',
        'data': [serialize_product(p) for p in products],
    })


@product_bp.route('/products', methods=['POST'])
@admin_required
def create_product():
    """POST /products — Create a new product (admin only)."""
    fields, err = extract_product_fields()
    if err:
        return err

    product = Product(name=fields['name'], price=fields['price'], stock=fields['stock'])
    db.session.add(product)
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': serialize_product(product),
    }), 201
