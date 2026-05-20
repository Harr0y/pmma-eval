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
from models import Product
from app import db

product_bp = Blueprint('product_bp', __name__)


def serialize_product(p):
    """Serialize a Product model instance to a dict."""
    return {"id": p.id, "name": p.name, "price": p.price, "stock": p.stock}


def error_response(message, status_code):
    """Return a unified error response."""
    return jsonify({"status": "error", "message": message}), status_code


@product_bp.route('/products', methods=['POST'])
def create_product():
    """Create a new product.

    Requires JSON body with name (str), price (float), stock (int).
    Returns 201 on success, 400 if any required field is missing.
    """
    data = request.get_json(silent=True)
    if data is None:
        return error_response("Request body must be valid JSON", 400)

    name = data.get('name')
    price = data.get('price')
    stock = data.get('stock')

    if name is None or price is None or stock is None:
        return error_response("Missing required fields: name, price, stock", 400)

    try:
        product = Product(name=name, price=float(price), stock=int(stock))
    except (ValueError, TypeError):
        return error_response("Invalid field types: price must be a number, stock must be an integer", 400)

    db.session.add(product)
    db.session.commit()

    return jsonify({"status": "ok", "data": serialize_product(product)}), 201


@product_bp.route('/products', methods=['GET'])
def list_products():
    """List all products.

    Returns 200 with a list of all product dicts.
    """
    products = Product.query.all()
    return jsonify({"status": "ok", "data": [serialize_product(p) for p in products]}), 200


@product_bp.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    """Get a single product by ID.

    Returns 200 with the product dict, or 404 if not found.
    """
    product = Product.query.get(product_id)
    if product is None:
        return error_response("Product not found", 404)

    return jsonify({"status": "ok", "data": serialize_product(product)}), 200
