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

from models import Product, db
from middleware import get_current_user

product_bp = Blueprint('product_bp', __name__)


@product_bp.route('/products', methods=['GET'])
def list_products():
    """List all products. No authentication required."""
    products = Product.query.all()
    return jsonify({
        'status': 'ok',
        'data': [p.to_dict() for p in products],
    }), 200


@product_bp.route('/products', methods=['POST'])
def create_product():
    """Create a new product. Admin only."""
    user = get_current_user()
    if user is None:
        return jsonify({
            'status': 'error',
            'message': 'Authentication required: missing or invalid X-User-Id header',
        }), 401

    if user.role != 'admin':
        return jsonify({
            'status': 'error',
            'message': 'Admin access required',
        }), 403

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({
            'status': 'error',
            'message': 'Request body must be valid JSON',
        }), 400

    # Validate required fields
    name = data.get('name')
    price = data.get('price')
    stock = data.get('stock')

    if name is None or not isinstance(name, str) or name.strip() == '':
        return jsonify({
            'status': 'error',
            'message': 'Missing or invalid field: name (required, non-empty string)',
        }), 400

    if price is None or not isinstance(price, (int, float)):
        return jsonify({
            'status': 'error',
            'message': 'Missing or invalid field: price (required, number)',
        }), 400

    if stock is None or not isinstance(stock, int) or isinstance(stock, bool):
        return jsonify({
            'status': 'error',
            'message': 'Missing or invalid field: stock (required, integer)',
        }), 400

    product = Product(name=name.strip(), price=float(price), stock=stock)
    db.session.add(product)
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': product.to_dict(),
    }), 201
