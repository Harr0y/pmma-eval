"""
T2 Order System -- Product Routes (Gen 1, Sample 2)

Design decisions (intentionally different from a naive implementation):
1. Uses a standalone serialize() helper function to decouple model-to-dict
   conversion from route handlers, making serialization reusable and testable.
2. Explicit field validation via a dedicated _validate_product_fields() function
   that returns structured error info instead of ad-hoc checks inside handlers.
3. Every route handler follows the same three-phase pattern:
     validate -> execute -> serialize, keeping logic flat and predictable.
"""

from flask import Blueprint, request, jsonify

from app import db
from models import Product

product_bp = Blueprint('product_bp', __name__)


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------

def serialize(product):
    """Convert a Product ORM instance into a plain dict."""
    return {
        'id': product.id,
        'name': product.name,
        'price': product.price,
        'stock': product.stock,
    }


def serialize_list(products):
    """Convert an iterable of Product instances into a list of dicts."""
    return [serialize(p) for p in products]


# ---------------------------------------------------------------------------
# Field validation
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = {'name', 'price', 'stock'}
_TYPE_COERCION = {
    'name': str,
    'price': (int, float),
    'stock': int,
}


def _validate_product_fields(payload):
    """Validate product creation payload.

    Returns (cleaned_data_dict, error_message_tuple_or_None).
    The error_message_tuple is (field_name, description) suitable for
    building a user-facing error response.
    """
    # Check for missing keys
    missing = _REQUIRED_FIELDS - set(payload.keys())
    if missing:
        return None, (', '.join(sorted(missing)), 'missing required field(s)')

    # Check types and coerce where possible
    cleaned = {}
    for field, expected_type in _TYPE_COERCION.items():
        value = payload[field]
        if not isinstance(value, expected_type):
            return None, (field, f'expected {expected_type.__name__}, got {type(value).__name__}')
        cleaned[field] = value

    # Price must be non-negative
    if cleaned['price'] < 0:
        return None, ('price', 'must be non-negative')

    # Stock must be non-negative
    if cleaned['stock'] < 0:
        return None, ('stock', 'must be non-negative')

    return cleaned, None


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

@product_bp.route('/products', methods=['GET'])
def list_products():
    """GET /products -- return all products."""
    products = Product.query.all()
    return jsonify({'status': 'ok', 'data': serialize_list(products)}), 200


@product_bp.route('/products', methods=['POST'])
def create_product():
    """POST /products -- create a new product.

    Required JSON body: {name: str, price: float, stock: int}
    """
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({'status': 'error', 'message': 'request body must be JSON'}), 400

    cleaned, err = _validate_product_fields(payload)
    if err is not None:
        field, description = err
        return jsonify({'status': 'error', 'message': f'Invalid field "{field}": {description}'}), 400

    product = Product(name=cleaned['name'], price=float(cleaned['price']), stock=int(cleaned['stock']))
    db.session.add(product)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': serialize(product)}), 201


@product_bp.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    """GET /products/<id> -- return a single product."""
    product = Product.query.get(product_id)
    if product is None:
        return jsonify({'status': 'error', 'message': f'Product {product_id} not found'}), 404

    return jsonify({'status': 'ok', 'data': serialize(product)}), 200
