"""
T2 Order System — Product Routes
"""

from flask import Blueprint, request, jsonify
from models import Product, db

product_bp = Blueprint('product_bp', __name__)


@product_bp.route('/products', methods=['GET'])
def list_products():
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
    body = request.get_json(silent=True)
    if not body or 'name' not in body or 'price' not in body or 'stock' not in body:
        return jsonify({'status': 'error', 'message': 'Missing required fields: name, price, stock'}), 400

    p = Product(name=body['name'], price=float(body['price']), stock=int(body['stock']))
    db.session.add(p)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': {
        'id': p.id,
        'name': p.name,
        'price': p.price,
        'stock': p.stock
    }}), 201


@product_bp.route('/products/<int:pid>', methods=['GET'])
def get_product(pid):
    p = Product.query.get(pid)
    if not p:
        return jsonify({'status': 'error', 'message': 'Product not found'}), 404

    return jsonify({'status': 'ok', 'data': {
        'id': p.id,
        'name': p.name,
        'price': p.price,
        'stock': p.stock
    }})
