"""
T2 Order System — Product Routes
"""

from flask import Blueprint, request, jsonify
from app import db
from models import Product

product_bp = Blueprint('product_bp', __name__)


def _product_to_dict(p):
    return {
        'id': p.id,
        'name': p.name,
        'price': p.price,
        'stock': p.stock,
    }


@product_bp.route('/products', methods=['POST'])
def create_product():
    data = request.get_json()
    if not data or 'name' not in data or 'price' not in data or 'stock' not in data:
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400
    p = Product(name=data['name'], price=float(data['price']), stock=int(data['stock']))
    db.session.add(p)
    db.session.commit()
    return jsonify({'status': 'ok', 'data': _product_to_dict(p)}), 201


@product_bp.route('/products', methods=['GET'])
def list_products():
    products = Product.query.all()
    return jsonify({'status': 'ok', 'data': [_product_to_dict(p) for p in products]}), 200


@product_bp.route('/products/<int:pid>', methods=['GET'])
def get_product(pid):
    p = Product.query.get(pid)
    if not p:
        return jsonify({'status': 'error', 'message': 'Product not found'}), 404
    return jsonify({'status': 'ok', 'data': _product_to_dict(p)}), 200
