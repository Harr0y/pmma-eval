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
from models import Product, db

product_bp = Blueprint('product_bp', __name__)


@product_bp.route('/products', methods=['GET'])
def list_products():
    """List all products."""
    products = Product.query.all()
    data = [
        {"id": p.id, "name": p.name, "price": p.price, "stock": p.stock}
        for p in products
    ]
    return jsonify({"status": "ok", "data": data}), 200


@product_bp.route('/products', methods=['POST'])
def create_product():
    """Create a new product."""
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"status": "error", "message": "Request body must be JSON"}), 400

    for field in ("name", "price", "stock"):
        if field not in body:
            return jsonify({"status": "error", "message": f"Missing required field: {field}"}), 400

    product = Product(name=body["name"], price=body["price"], stock=body["stock"])
    db.session.add(product)
    db.session.commit()

    data = {
        "id": product.id,
        "name": product.name,
        "price": product.price,
        "stock": product.stock,
    }
    return jsonify({"status": "ok", "data": data}), 201


@product_bp.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    """Get a single product by ID."""
    product = Product.query.get(product_id)
    if product is None:
        return jsonify({"status": "error", "message": "Product not found"}), 404

    data = {
        "id": product.id,
        "name": product.name,
        "price": product.price,
        "stock": product.stock,
    }
    return jsonify({"status": "ok", "data": data}), 200
