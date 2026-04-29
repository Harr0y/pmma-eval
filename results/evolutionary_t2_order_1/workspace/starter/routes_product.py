"""
T2 Order System -- Product Routes (Gen 1 Sample 1)

Implementation strategy: thin service-layer approach.
Instead of inlining all logic inside route handlers, I extract a small
private helper (_serialize_product) to centralise the dict conversion.
This keeps the route bodies clean and makes the serialization contract
explicit in one place -- easier to evolve if Product fields change.

Validation is done eagerly before touching the database, and I prefer
explicit field-by-field checks over generic schema libraries to keep
the dependency footprint minimal.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Blueprint, request, jsonify
from app import db
from models import Product

product_bp = Blueprint('product_bp', __name__)


def _serialize_product(product):
    """Convert a Product ORM object to a plain dict for JSON responses."""
    return {
        'id': product.id,
        'name': product.name,
        'price': product.price,
        'stock': product.stock,
    }


@product_bp.route('/products', methods=['GET'])
def list_products():
    products = Product.query.all()
    return jsonify({
        'status': 'ok',
        'data': [_serialize_product(p) for p in products],
    }), 200


@product_bp.route('/products', methods=['POST'])
def create_product():
    body = request.get_json(silent=True)

    # Validate that the body is a dict and contains all required keys.
    if not isinstance(body, dict):
        return jsonify({
            'status': 'error',
            'message': 'Request body must be a JSON object',
        }), 400

    required_fields = ('name', 'price', 'stock')
    missing = [f for f in required_fields if f not in body]
    if missing:
        return jsonify({
            'status': 'error',
            'message': f'Missing required fields: {", ".join(missing)}',
        }), 400

    # Basic type validation -- fail fast before writing to DB.
    name = body['name']
    price = body['price']
    stock = body['stock']

    if not isinstance(name, str) or not name.strip():
        return jsonify({
            'status': 'error',
            'message': '"name" must be a non-empty string',
        }), 400

    if not isinstance(price, (int, float)):
        return jsonify({
            'status': 'error',
            'message': '"price" must be a number',
        }), 400

    if not isinstance(stock, int):
        return jsonify({
            'status': 'error',
            'message': '"stock" must be an integer',
        }), 400

    product = Product(name=name.strip(), price=float(price), stock=stock)
    db.session.add(product)
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': _serialize_product(product),
    }), 201


@product_bp.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    product = Product.query.get(product_id)
    if product is None:
        return jsonify({
            'status': 'error',
            'message': f'Product with id {product_id} not found',
        }), 404

    return jsonify({
        'status': 'ok',
        'data': _serialize_product(product),
    }), 200
