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

from models import db, Product
from middleware import get_current_user

product_bp = Blueprint('product_bp', __name__)


@product_bp.route('/products', methods=['GET'])
def list_products():
    """List all products."""
    products = Product.query.all()
    data = [{
        'id': p.id,
        'name': p.name,
        'price': p.price,
        'stock': p.stock,
    } for p in products]
    return jsonify({'status': 'ok', 'data': data})


@product_bp.route('/products', methods=['POST'])
def create_product():
    """Create a new product (admin only)."""
    user = get_current_user()
    if not user:
        return jsonify({'status': 'error', 'message': 'Authentication required'}), 401
    if user.role != 'admin':
        return jsonify({'status': 'error', 'message': 'Admin access required'}), 403

    data = request.get_json()
    if not data or not data.get('name') or data.get('price') is None or data.get('stock') is None:
        return jsonify({'status': 'error', 'message': 'Invalid input'}), 400

    product = Product(
        name=data['name'],
        price=float(data['price']),
        stock=int(data['stock']),
    )
    db.session.add(product)
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': {
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'stock': product.stock,
        }
    }), 201
