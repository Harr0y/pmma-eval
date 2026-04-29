"""
T2 Order System — Product Routes

Implement product CRUD routes.
Register as a Flask Blueprint named 'product_bp'.

Requirements:
- GET /products -> List all products
  Response: {"status": "ok", "data": [{"id": int, "name": str, "price": float, "stock": int}, ...]}

- POST /products -> Create product
  Request: {"name": str, "price": float, "stock": int}
  Response: {"status": "ok", "data": {"id": int, "name": str, "price": float, "stock": int}}
  Errors: 400 if any required field missing

- GET /products/<id> -> Get single product
  Response: {"status": "ok", "data": {"id": int, "name": str, "price": float, "stock": int}}
  Errors: 404 if not found

IMPORTANT: Products are used by routes_order.py for inventory management.
Make sure the Product model fields match what the order routes expect.
"""

from flask import Blueprint, request, jsonify
from app import db
from models import Product

product_bp = Blueprint('product_bp', __name__)


def product_to_dict(product):
    """Serialize a Product model instance to a dictionary."""
    return {
        'id': product.id,
        'name': product.name,
        'price': product.price,
        'stock': product.stock,
    }


def error_response(status_code, message):
    """Return a unified error response."""
    return jsonify({"status": "error", "message": message}), status_code


def ok_response(data, status_code=200):
    """Return a unified success response."""
    return jsonify({"status": "ok", "data": data}), status_code


@product_bp.route('/products', methods=['POST'])
def create_product():
    """Create a new product. Requires name, price, and stock in JSON body."""
    body = request.get_json(silent=True)
    if body is None:
        return error_response(400, "Request body must be valid JSON")

    name = body.get('name')
    price = body.get('price')
    stock = body.get('stock')

    # Validate required fields
    if name is None or name == '':
        return error_response(400, "Field 'name' is required")
    if price is None:
        return error_response(400, "Field 'price' is required")
    if stock is None:
        return error_response(400, "Field 'stock' is required")

    # Validate types
    if not isinstance(price, (int, float)):
        return error_response(400, "Field 'price' must be a number")
    if not isinstance(stock, int):
        return error_response(400, "Field 'stock' must be an integer")

    # Validate value constraints
    if price < 0:
        return error_response(400, "Field 'price' must be non-negative")
    if stock < 0:
        return error_response(400, "Field 'stock' must be non-negative")

    product = Product(name=name, price=float(price), stock=stock)
    db.session.add(product)
    db.session.commit()

    return ok_response(product_to_dict(product), status_code=201)


@product_bp.route('/products', methods=['GET'])
def list_products():
    """List all products."""
    products = Product.query.all()
    return ok_response([product_to_dict(p) for p in products])


@product_bp.route('/products/<int:id>', methods=['GET'])
def get_product(id):
    """Get a single product by ID. Returns 404 if not found."""
    product = Product.query.get_or_404(id)
    return ok_response(product_to_dict(product))
