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


def serialize_product(product):
    """Serialize a Product model instance to a plain dict.

    Spec: design.md section 4 — serialization helper functions.
    """
    return {
        "id": product.id,
        "name": product.name,
        "price": product.price,
        "stock": product.stock,
    }


@product_bp.route('/products', methods=['GET'])
def list_products():
    """List all products.

    Spec: design.md section 2.1 — GET /products.
    Returns 200 with {"status": "ok", "data": [...]}.
    When no products exist, data is an empty list [].
    """
    products = Product.query.all()
    return jsonify({
        "status": "ok",
        "data": [serialize_product(p) for p in products],
    }), 200


@product_bp.route('/products', methods=['POST'])
def create_product():
    """Create a new product.

    Spec: design.md section 2.1 — POST /products.
    1. Defensive check: request.json is None -> 400 "Request body must be JSON"
    2. Validate that name, price, stock all exist and are not None -> 400 with field name
    3. Create Product record, db.session.commit()
    4. Return 201 + {"status": "ok", "data": {...}}
    """
    # Defensive check: request.json is None
    if request.json is None:
        return jsonify({
            "status": "error",
            "message": "Request body must be JSON",
        }), 400

    data = request.json

    # Validate required fields: name, price, stock
    required_fields = ["name", "price", "stock"]
    for field in required_fields:
        if field not in data or data[field] is None:
            return jsonify({
                "status": "error",
                "message": f"Missing required field: {field}",
            }), 400

    product = Product(
        name=data["name"],
        price=data["price"],
        stock=data["stock"],
    )
    db.session.add(product)
    db.session.commit()

    return jsonify({
        "status": "ok",
        "data": serialize_product(product),
    }), 201


@product_bp.route('/products/<int:id>', methods=['GET'])
def get_product(id):
    """Get a single product by ID.

    Spec: design.md section 2.1 — GET /products/<id>.
    Returns 404 if product does not exist.
    Returns 200 + {"status": "ok", "data": {...}} on success.
    """
    product = Product.query.get(id)
    if product is None:
        return jsonify({
            "status": "error",
            "message": "Product not found",
        }), 404

    return jsonify({
        "status": "ok",
        "data": serialize_product(product),
    }), 200
