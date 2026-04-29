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
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app import db
from models import Product
from middleware import get_current_user

product_bp = Blueprint('product_bp', __name__)


@product_bp.route('/products', methods=['GET'])
def get_products():
    """List all products. No authentication required."""
    products = Product.query.all()
    return jsonify({
        "status": "ok",
        "data": [product.to_dict() for product in products],
    }), 200


@product_bp.route('/products', methods=['POST'])
def create_product():
    """Create a new product. Requires admin role."""
    user = get_current_user()
    if user is None:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    if user.role != 'admin':
        return jsonify({"status": "error", "message": "Forbidden"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON"}), 400

    # Validate name: must exist and be non-empty
    name = data.get('name')
    if not name or not isinstance(name, str) or name.strip() == '':
        return jsonify({"status": "error", "message": "Name is required and must be a non-empty string"}), 400

    # Validate price: must exist and be a positive number
    price = data.get('price')
    if price is None:
        return jsonify({"status": "error", "message": "Price is required"}), 400
    try:
        price = float(price)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Price must be a valid number"}), 400
    if price <= 0:
        return jsonify({"status": "error", "message": "Price must be a positive number"}), 400

    # Validate stock: must exist and be a non-negative integer
    stock = data.get('stock')
    if stock is None:
        return jsonify({"status": "error", "message": "Stock is required"}), 400
    try:
        stock = int(stock)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Stock must be a valid integer"}), 400
    if stock < 0:
        return jsonify({"status": "error", "message": "Stock must be a non-negative integer"}), 400

    product = Product(name=name.strip(), price=price, stock=stock)
    db.session.add(product)
    db.session.commit()

    return jsonify({
        "status": "ok",
        "data": product.to_dict(),
    }), 201
