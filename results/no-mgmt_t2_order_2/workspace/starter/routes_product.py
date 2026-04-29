"""
T2 Order System - Product Routes

Implement product CRUD routes.
Register as a Flask Blueprint named 'product_bp'.
"""

from flask import Blueprint, request, jsonify
from models import db, Product

product_bp = Blueprint('product_bp', __name__)


@product_bp.route('/products', methods=['POST'])
def create_product():
    data = request.get_json()
    if not data or not all(k in data for k in ('name', 'price', 'stock')):
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400

    product = Product(name=data['name'], price=float(data['price']), stock=int(data['stock']))
    db.session.add(product)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': {
        'id': product.id,
        'name': product.name,
        'price': product.price,
        'stock': product.stock,
    }}), 201


@product_bp.route('/products', methods=['GET'])
def list_products():
    products = Product.query.all()
    data = [{
        'id': p.id,
        'name': p.name,
        'price': p.price,
        'stock': p.stock,
    } for p in products]
    return jsonify({'status': 'ok', 'data': data}), 200


@product_bp.route('/products/<int:pid>', methods=['GET'])
def get_product(pid):
    product = Product.query.get(pid)
    if not product:
        return jsonify({'status': 'error', 'message': 'Product not found'}), 404

    return jsonify({'status': 'ok', 'data': {
        'id': product.id,
        'name': product.name,
        'price': product.price,
        'stock': product.stock,
    }}), 200
