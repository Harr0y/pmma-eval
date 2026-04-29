"""
T3 E-commerce -- Product Routes (Sample 1: Decorator-First Validation)

Strategy: Use a custom @require_admin decorator to separate auth logic
from business logic entirely. Input validation is performed in a dedicated
helper, and serialization is extracted into a standalone function.

This keeps route handlers thin and focused on their core responsibility.
"""

from functools import wraps
from flask import Blueprint, request, jsonify

from models import Product, db
from middleware import get_current_user

product_bp = Blueprint('product_bp', __name__)


# ---- Decorators ----

def require_admin(fn):
    """Decorator that enforces authentication + admin authorization.

    Returns 401 if X-User-Id is missing or invalid.
    Returns 403 if the user is not an admin.
    Otherwise passes the authenticated User object as `current_user` kwarg.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return jsonify({
                'status': 'error',
                'message': 'Authentication required: provide a valid X-User-Id header',
            }), 401
        if user.role != 'admin':
            return jsonify({
                'status': 'error',
                'message': 'Forbidden: admin access required',
            }), 403
        kwargs['current_user'] = user
        return fn(*args, **kwargs)
    return wrapper


# ---- Helpers ----

def _serialize_product(product):
    """Convert a Product ORM object to a plain dict for JSON response."""
    return {
        'id': product.id,
        'name': product.name,
        'price': product.price,
        'stock': product.stock,
    }


def _validate_create_payload(data):
    """Validate and extract fields from a create-product request body.

    Returns (fields_dict, error_response) where error_response is None
    when validation succeeds, or a (json, status_code) tuple on failure.
    """
    if not data or not isinstance(data, dict):
        return None, (jsonify({'status': 'error', 'message': 'Request body must be a JSON object'}), 400)

    name = data.get('name')
    if not name or not isinstance(name, str) or not name.strip():
        return None, (jsonify({'status': 'error', 'message': 'Invalid or missing "name"'}), 400)

    try:
        price = float(data['price'])
        if price < 0:
            return None, (jsonify({'status': 'error', 'message': 'Price must be non-negative'}), 400)
    except (KeyError, TypeError, ValueError):
        return None, (jsonify({'status': 'error', 'message': 'Invalid or missing "price"'}), 400)

    try:
        stock = int(data['stock'])
        if stock < 0:
            return None, (jsonify({'status': 'error', 'message': 'Stock must be non-negative'}), 400)
    except (KeyError, TypeError, ValueError):
        return None, (jsonify({'status': 'error', 'message': 'Invalid or missing "stock"'}), 400)

    return {'name': name.strip(), 'price': price, 'stock': stock}, None


# ---- Routes ----

@product_bp.route('/products', methods=['GET'])
def list_products():
    """Return all products as a JSON array."""
    products = Product.query.order_by(Product.id).all()
    return jsonify({
        'status': 'ok',
        'data': [_serialize_product(p) for p in products],
    })


@product_bp.route('/products', methods=['POST'])
@require_admin
def create_product(current_user=None):
    """Create a new product. Admin access required."""
    fields, error = _validate_create_payload(request.get_json(silent=True))
    if error:
        return error

    product = Product(name=fields['name'], price=fields['price'], stock=fields['stock'])
    db.session.add(product)
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': _serialize_product(product),
    }), 201
