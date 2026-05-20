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


@product_bp.route('/products', methods=['POST'])
def create_product():
    data = request.get_json()
    if not data or 'name' not in data or 'price' not in data or 'stock' not in data:
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400
    product = Product(name=data['name'], price=data['price'], stock=data['stock'])
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


@product_bp.route('/products', methods=['GET'])
def list_products():
    products = Product.query.all()
    return jsonify({
        'status': 'ok',
        'data': [
            {'id': p.id, 'name': p.name, 'price': p.price, 'stock': p.stock}
            for p in products
        ]
    }), 200


@product_bp.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    product = db.session.get(Product, product_id)
    if product is None:
        return jsonify({'status': 'error', 'message': 'Product not found'}), 404
    return jsonify({
        'status': 'ok',
        'data': {
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'stock': product.stock,
        }
    }), 200
