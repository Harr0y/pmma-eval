"""
routes_product_sample1.py — Functional-style Product CRUD routes (Gen 1 Sample 1)

Mutation strategy:
- Pure functions for each route handler (no class wrapping)
- Dictionary comprehensions for data serialization
- Explicit try-except error handling patterns
- db.session.get() for object retrieval by primary key
"""

from flask import Blueprint, request, jsonify
from models import Product, db

product_bp = Blueprint('product_bp', __name__)


def _serialize_product(product):
    """Serialize a single Product ORM object to a plain dict."""
    return {
        key: getattr(product, key)
        for key in ('id', 'name', 'price', 'stock')
    }


def _serialize_products(products):
    """Serialize a list of Product ORM objects to a list of dicts."""
    return [_serialize_product(p) for p in products]


def _success_response(data, status_code=200):
    """Build a standardized success JSON response."""
    return jsonify({"status": "ok", "data": data}), status_code


def _error_response(message, status_code=400):
    """Build a standardized error JSON response."""
    return jsonify({"status": "error", "message": message}), status_code


@product_bp.route('/products', methods=['GET'])
def list_products():
    """GET /products — Return all products as a JSON array."""
    try:
        all_products = Product.query.all()
        return _success_response(_serialize_products(all_products))
    except Exception as exc:
        return _error_response(str(exc), 500)


@product_bp.route('/products', methods=['POST'])
def create_product():
    """POST /products — Create a new product from JSON payload."""
    try:
        payload = request.get_json(silent=True)

        if payload is None:
            return _error_response("Request body must be valid JSON", 400)

        name = payload.get('name')
        price = payload.get('price')
        stock = payload.get('stock')

        if not name:
            return _error_response("Missing required field: name", 400)
        if price is None:
            return _error_response("Missing required field: price", 400)
        if stock is None:
            return _error_response("Missing required field: stock", 400)

        product = Product(name=name, price=float(price), stock=int(stock))
        db.session.add(product)
        db.session.commit()

        return _success_response(_serialize_product(product), 201)

    except Exception as exc:
        db.session.rollback()
        return _error_response(str(exc), 400)


@product_bp.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    """GET /products/<id> — Retrieve a single product by its primary key."""
    try:
        product = db.session.get(Product, product_id)

        if product is None:
            return _error_response(f"Product {product_id} not found", 404)

        return _success_response(_serialize_product(product))

    except Exception as exc:
        return _error_response(str(exc), 500)
