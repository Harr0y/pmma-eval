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

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from flask import Blueprint, request, jsonify
from models import Product
from middleware import get_current_user
from app import db

product_bp = Blueprint('product_bp', __name__)


@product_bp.route('/products', methods=['GET'])
def list_products():
    """List all products. No authentication required.

    design.md Section 3.1 / FR-002-1, FR-002-2
    """
    products = Product.query.all()
    data = [{
        'id': p.id,
        'name': p.name,
        'price': p.price,
        'stock': p.stock
    } for p in products]
    return jsonify({'status': 'ok', 'data': data})


@product_bp.route('/products', methods=['POST'])
def create_product():
    """Create a new product. Admin only.

    design.md Section 3.2 / FR-002-3, FR-002-4, FR-002-5, FR-002-6, FR-002-7

    Flow:
    1. Authenticate via X-User-Id header
    2. Authorize: user.role must be 'admin'
    3. Validate request body (name, price, stock)
    4. Create Product and return 201
    """
    # Step 1: Authentication
    user = get_current_user()
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    # Step 2: Authorization — admin only
    if user.role != 'admin':
        return jsonify({'status': 'error', 'message': 'Forbidden'}), 403

    # Step 3: Parse and validate request body
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    name = data.get('name')
    price = data.get('price')
    stock = data.get('stock')

    # Validate required fields are present
    if name is None or price is None or stock is None:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    # Validate field types and values (Section 7: implicit requirements)
    # name must be a non-empty string
    if not isinstance(name, str) or not name.strip():
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    # price must be a number and positive
    try:
        price_val = float(price)
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400
    if price_val <= 0:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    # stock must be an integer and non-negative
    try:
        stock_val = int(stock)
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400
    if stock_val < 0:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    # Step 4: Create Product
    product = Product(name=name.strip(), price=price_val, stock=stock_val)
    db.session.add(product)
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': {
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'stock': product.stock
        }
    }), 201
