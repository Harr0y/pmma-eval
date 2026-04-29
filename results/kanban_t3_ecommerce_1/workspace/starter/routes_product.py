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

from models import Product
from middleware import get_current_user

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
    """Create a new product (Admin only)."""
    user = get_current_user()
    if user is None:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    if user.role != 'admin':
        return jsonify({"status": "error", "message": "Forbidden"}), 403

    data = request.get_json()
    name = data.get('name')
    price = data.get('price')
    stock = data.get('stock')

    if not name or price is None or stock is None:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    product = Product(name=name, price=price, stock=stock)
    from app import db
    db.session.add(product)
    db.session.commit()

    return jsonify({
        "status": "ok",
        "data": {
            "id": product.id,
            "name": product.name,
            "price": product.price,
            "stock": product.stock,
        }
    }), 201
