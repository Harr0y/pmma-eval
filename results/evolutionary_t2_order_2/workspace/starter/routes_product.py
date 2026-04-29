"""
T2 Order System — Product Routes (Sample 2)

Evolutionary variant: uses standalone serializer functions
rather than model methods or inline dict construction.
This keeps serialization concerns separated from both
the ORM model and the route handlers.
"""

from flask import Blueprint, request, jsonify
from app import db
from models import Product

product_bp = Blueprint('product_bp', __name__)


# ── Serialization layer ──────────────────────────────────────

def serialize_product(product):
    """Convert a single Product ORM object to a plain dict.

    Designed to be reused by order routes when they need to
    embed product details in order responses.
    """
    return {
        'id': product.id,
        'name': product.name,
        'price': product.price,
        'stock': product.stock,
    }


def serialize_products(products):
    """Serialize a single product or a list of products.

    Accepts either a Product instance or an iterable of Products,
    so callers don't need to think about single-vs-list branching.
    """
    if products is None:
        return []
    if isinstance(products, Product):
        return serialize_product(products)
    return [serialize_product(p) for p in products]


# ── Response helpers ─────────────────────────────────────────

def error_response(message, status_code):
    """Build a standardized error JSON response."""
    body = {'status': 'error', 'message': message}
    return jsonify(body), status_code


def ok_response(data, status_code=200):
    """Build a standardized success JSON response."""
    body = {'status': 'ok', 'data': data}
    return jsonify(body), status_code


# ── Routes ───────────────────────────────────────────────────

@product_bp.route('/products', methods=['GET'])
def list_products():
    products = Product.query.all()
    return ok_response(serialize_products(products))


@product_bp.route('/products', methods=['POST'])
def create_product():
    payload = request.get_json(silent=True)
    if payload is None:
        return error_response('Request body must be valid JSON', 400)

    required_fields = ('name', 'price', 'stock')
    for field in required_fields:
        if field not in payload:
            return error_response(f'Missing required field: {field}', 400)

    product = Product(
        name=payload['name'],
        price=float(payload['price']),
        stock=int(payload['stock']),
    )
    db.session.add(product)
    db.session.commit()

    return ok_response(serialize_product(product), status_code=201)


@product_bp.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    product = Product.query.get(product_id)
    if product is None:
        return error_response(f'Product {product_id} not found', 404)

    return ok_response(serialize_product(product))
