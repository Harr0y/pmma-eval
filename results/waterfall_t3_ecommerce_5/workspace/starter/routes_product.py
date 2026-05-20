"""
T3 E-commerce — Product Routes

Implement product management routes.
Register as a Flask Blueprint named 'product_bp'.

Requirements:
- GET /products -> List all products
  Response: {"status": "ok", "data": [...]}
  Each product: {"id": int, "name": str, "price": float, "stock": int}

- POST /products -> Create product (Admin only)
  Request: {"name": str, "price": float, "stock": int}
  Response: {"status": "ok", "data": {...}}
  Errors: 403 if not admin, 400/401 if no user_id

Use middleware.get_current_user() to get the authenticated user.
"""

from flask import Blueprint, request, jsonify

product_bp = Blueprint('product_bp', __name__)

from middleware import get_current_user
from models import Product
from app import db


@product_bp.route('/products', methods=['GET'])
def get_products():
    """GET /products — List all products. No authentication required."""
    products = Product.query.all()
    data = [
        {"id": p.id, "name": p.name, "price": p.price, "stock": p.stock}
        for p in products
    ]
    return jsonify({"status": "ok", "data": data}), 200


@product_bp.route('/products', methods=['POST'])
def create_product():
    """POST /products — Create a new product. Admin only."""
    # Step 1: Authenticate via X-User-Id (design.md §2.2)
    user = get_current_user()
    if user is None:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    # Step 2: RBAC check — only admin can create products (design.md §2.2)
    if user.role != 'admin':
        return jsonify({"status": "error", "message": "Admin access required"}), 403

    # Step 3: Validate request body fields (design.md §3.3)
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"status": "error", "message": "Request body must be JSON"}), 400

    name = body.get('name')
    price = body.get('price')
    stock = body.get('stock')

    if not name or not isinstance(name, str):
        return jsonify({"status": "error", "message": "Missing or invalid field: name"}), 400
    if price is None or not isinstance(price, (int, float)):
        return jsonify({"status": "error", "message": "Missing or invalid field: price"}), 400
    if stock is None or not isinstance(stock, int):
        return jsonify({"status": "error", "message": "Missing or invalid field: stock"}), 400

    # Step 4: Create product and commit (design.md §2.2)
    product = Product(name=name, price=float(price), stock=stock)
    db.session.add(product)
    db.session.commit()

    return jsonify({
        "status": "ok",
        "data": {"id": product.id, "name": product.name, "price": product.price, "stock": product.stock}
    }), 201
