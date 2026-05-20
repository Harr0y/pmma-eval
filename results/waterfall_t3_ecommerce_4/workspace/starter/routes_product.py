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
from middleware import get_current_user
from models import Product
from app import db

product_bp = Blueprint('product_bp', __name__)


@product_bp.route('/products', methods=['GET'])
def get_products():
    """List all products. No authentication required."""
    products = Product.query.all()
    data = [
        {"id": p.id, "name": p.name, "price": p.price, "stock": p.stock}
        for p in products
    ]
    return jsonify({"status": "ok", "data": data}), 200


@product_bp.route('/products', methods=['POST'])
def create_product():
    """Create a new product. Admin only."""
    user = get_current_user()
    if user is None:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    if user.role != 'admin':
        return jsonify({"status": "error", "message": "Admin only"}), 403

    body = request.get_json(silent=True)
    if not body:
        return jsonify({"status": "error", "message": "Request body must be JSON"}), 400

    name = body.get('name')
    price = body.get('price')
    stock = body.get('stock')

    if not name or price is None or stock is None:
        return jsonify({"status": "error", "message": "Missing required fields: name, price, stock"}), 400

    if not isinstance(name, str) or name.strip() == '':
        return jsonify({"status": "error", "message": "name must be a non-empty string"}), 400

    try:
        price = float(price)
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "price must be a number"}), 400

    try:
        stock = int(stock)
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "stock must be an integer"}), 400

    if price <= 0:
        return jsonify({"status": "error", "message": "price must be a positive number"}), 400

    if stock < 0:
        return jsonify({"status": "error", "message": "stock must be a non-negative integer"}), 400

    product = Product(name=name, price=price, stock=stock)
    db.session.add(product)
    db.session.commit()

    return jsonify({
        "status": "ok",
        "data": {"id": product.id, "name": product.name, "price": product.price, "stock": product.stock}
    }), 201
