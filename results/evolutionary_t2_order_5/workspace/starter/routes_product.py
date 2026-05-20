"""
T2 Order System - Product Routes (Sample 2: Class-based View + Serializer pattern)

Design decisions:
  - ResourceHandler class groups all serialization logic in one place
  - Guard clauses (early returns) for error handling, no deep nesting
  - Explicit field extraction via a _serialize method instead of to_dict()
  - Uses jsonify() consistently for all JSON responses
  - Blueprint name kept as 'product_bp' for drop-in compatibility

Author: Gen-1 Sample 2 (Evolutionary PM variant)
"""

from flask import Blueprint, request, jsonify
from models import Product, db

product_bp = Blueprint('product_bp', __name__)


# ---------------------------------------------------------------------------
# Serializer / Response builder
# ---------------------------------------------------------------------------

class ProductSerializer:
    """Marshmallow-inspired lightweight serializer for the Product model.

    Instead of putting serialization logic inside model methods or scattering
    it across route handlers, we centralise field extraction here.  This keeps
    the route handlers thin and makes it easy to change the public API shape
    without touching business logic.
    """

    # Public fields exposed by the API.
    FIELDS = ('id', 'name', 'price', 'stock')

    @classmethod
    def one(cls, product: Product) -> dict:
        """Serialize a single Product instance."""
        return {field: getattr(product, field) for field in cls.FIELDS}

    @classmethod
    def many(cls, products) -> list:
        """Serialize an iterable of Product instances."""
        return [cls.one(p) for p in products]


# ---------------------------------------------------------------------------
# Helper functions (guard-clause style)
# ---------------------------------------------------------------------------

def _find_product_or_abort(product_id: int):
    """Return a Product by PK or None.

    The caller decides how to respond (404), keeping the query logic
    separate from HTTP concerns.
    """
    return Product.query.get(product_id)


def _extract_create_fields(body: dict):
    """Validate and extract fields from the request body.

    Returns (fields_dict, error_tuple) where error_tuple is
    (status_code, message) on validation failure, or None on success.
    """
    required = ('name', 'price', 'stock')
    missing = [f for f in required if f not in body]
    if missing:
        return None, (400, f"Missing required fields: {', '.join(missing)}")

    name = body['name']
    if not isinstance(name, str) or not name.strip():
        return None, (400, "Field 'name' must be a non-empty string")

    try:
        price = float(body['price'])
    except (TypeError, ValueError):
        return None, (400, "Field 'price' must be a number")

    if price < 0:
        return None, (400, "Field 'price' cannot be negative")

    try:
        stock = int(body['stock'])
    except (TypeError, ValueError):
        return None, (400, "Field 'stock' must be an integer")

    if stock < 0:
        return None, (400, "Field 'stock' cannot be negative")

    return {'name': name.strip(), 'price': price, 'stock': stock}, None


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

@product_bp.route('/products', methods=['GET'])
def list_products():
    """GET /products - Return all products as a JSON list."""
    products = Product.query.all()
    return jsonify({
        'status': 'ok',
        'data': ProductSerializer.many(products),
    }), 200


@product_bp.route('/products', methods=['POST'])
def create_product():
    """POST /products - Create a new product.

    Accepts JSON body with name, price, stock.
    Returns 201 on success, 400 on validation error.
    """
    body = request.get_json(silent=True)

    # Guard: request body must be a dict
    if not isinstance(body, dict):
        return jsonify({
            'status': 'error',
            'message': 'Request body must be valid JSON',
        }), 400

    fields, error = _extract_create_fields(body)

    # Guard: validation failed
    if error is not None:
        status_code, message = error
        return jsonify({'status': 'error', 'message': message}), status_code

    product = Product(**fields)
    db.session.add(product)
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': ProductSerializer.one(product),
    }), 201


@product_bp.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id: int):
    """GET /products/<id> - Return a single product by ID.

    Returns 200 with product data, or 404 if not found.
    """
    product = _find_product_or_abort(product_id)

    # Guard: product not found
    if product is None:
        return jsonify({
            'status': 'error',
            'message': f'Product {product_id} not found',
        }), 404

    return jsonify({
        'status': 'ok',
        'data': ProductSerializer.one(product),
    }), 200
