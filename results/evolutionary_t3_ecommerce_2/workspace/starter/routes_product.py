"""
T3 E-commerce - Product Routes (Sample 1: Validation-First Approach)

Design decisions:
- Uses a dedicated _serialize helper to convert Product ORM objects to dicts,
  keeping route handlers thin and serialization logic in one place.
- Input validation is performed inline before touching the database,
  returning 400 for malformed requests early.
- Admin gate is a reusable _require_admin helper that returns (user, error_response),
  allowing each protected route to handle the tuple consistently.
- No JSON error body for 401/403 -- just status codes and a plain dict,
  matching the minimal style the tests expect.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from flask import Blueprint, request, jsonify
from models import Product, db
from middleware import get_current_user

product_bp = Blueprint('product_bp', __name__)


def _serialize(product):
    """Convert a Product ORM object to a plain dict."""
    return {
        'id': product.id,
        'name': product.name,
        'price': product.price,
        'stock': product.stock,
    }


def _require_admin():
    """Check admin access.

    Returns (user, error_response).
    - If user is authenticated and is admin: (User, None)
    - If no X-User-Id header: (None, 401 response)
    - If user is not admin: (User, 403 response)
    """
    user, auth_error = get_current_user()
    if auth_error:
        return None, auth_error
    if user.role != 'admin':
        return user, (jsonify({'status': 'error', 'message': 'Admin access required'}), 403)
    return user, None


@product_bp.route('/products', methods=['GET'])
def list_products():
    """List all products. No authentication required."""
    products = Product.query.all()
    return jsonify({'status': 'ok', 'data': [_serialize(p) for p in products]})


@product_bp.route('/products', methods=['POST'])
def create_product():
    """Create a new product. Admin only."""
    user, error = _require_admin()
    if error:
        return error

    body = request.get_json(silent=True)
    if body is None:
        return jsonify({'status': 'error', 'message': 'Invalid JSON'}), 400

    # Validate required fields
    name = body.get('name')
    price = body.get('price')
    stock = body.get('stock')

    if not name or not isinstance(name, str):
        return jsonify({'status': 'error', 'message': 'name is required and must be a string'}), 400
    if price is None or not isinstance(price, (int, float)):
        return jsonify({'status': 'error', 'message': 'price is required and must be a number'}), 400
    if stock is None or not isinstance(stock, int):
        return jsonify({'status': 'error', 'message': 'stock is required and must be an integer'}), 400

    product = Product(name=name, price=float(price), stock=stock)
    db.session.add(product)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize(product)}), 201
