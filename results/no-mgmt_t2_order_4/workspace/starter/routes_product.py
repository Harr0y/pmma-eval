"""
T2 Order System - Product Routes

Implement product CRUD routes.
Register as a Flask Blueprint named 'product_bp'.
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
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'status': 'error', 'message': 'Request body must be JSON'}), 400

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


@product_bp.route('/products/<int:pid>', methods=['GET'])
def get_product(pid):
    p = Product.query.get(pid)
    if not p:
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
