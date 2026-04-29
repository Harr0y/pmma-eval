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


@product_bp.route('/products', methods=['GET'])
def list_products():
    products = Product.query.all()
    data = [
        {
            'id': p.id,
            'name': p.name,
            'price': p.price,
            'stock': p.stock,
        }
        for p in products
    ]
    return jsonify({'status': 'ok', 'data': data})


@product_bp.route('/products', methods=['POST'])
def create_product():
    body = request.get_json(force=True)
    name = body.get('name')
    price = body.get('price')
    stock = body.get('stock')

    if name is None or price is None or stock is None:
        return jsonify({'status': 'error', 'message': 'Missing required fields: name, price, stock'}), 400

    p = Product(name=name, price=float(price), stock=int(stock))
    db.session.add(p)
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': {
            'id': p.id,
            'name': p.name,
            'price': p.price,
            'stock': p.stock,
        }
    }), 201


@product_bp.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    p = Product.query.get(product_id)
    if p is None:
        return jsonify({'status': 'error', 'message': 'Product not found'}), 404

    return jsonify({
        'status': 'ok',
        'data': {
            'id': p.id,
            'name': p.name,
            'price': p.price,
            'stock': p.stock,
        }
    })
