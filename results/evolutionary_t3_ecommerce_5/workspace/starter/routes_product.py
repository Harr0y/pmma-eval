"""
T3 E-commerce - Product Routes (Gen 1, Sample 1)

Implementation strategy:
- Use a dedicated serialize helper function (not a method) for product dict
  conversion, making the serialization logic independently testable.
- Adopt the "guard clause" / early-return pattern for error handling
  in POST, keeping the happy path at the top indentation level.
- Build response dicts inline via literal construction rather than
  constructing a mutable dict and filling fields incrementally.

Mutation notes:
- Serialization is factored into a standalone _product_to_dict() rather
  than embedded list comprehension or inline lambda -- this keeps the
  route handler thin and allows future schema changes in one place.
- Admin check is performed before reading request body (fail fast on
  auth) which differs from the common pattern of validating payload first.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Blueprint, request, jsonify
from models import Product
from middleware import get_current_user

product_bp = Blueprint('product_bp', __name__)


def _product_to_dict(product):
    """Serialize a Product ORM object into a plain dict."""
    return {
        "id": product.id,
        "name": product.name,
        "price": product.price,
        "stock": product.stock,
    }


# ── GET /products ────────────────────────────────────────────
@product_bp.route('/products', methods=['GET'])
def list_products():
    products = Product.query.all()
    return jsonify({
        "status": "ok",
        "data": [_product_to_dict(p) for p in products],
    })


# ── POST /products (Admin only) ─────────────────────────────
@product_bp.route('/products', methods=['POST'])
def create_product():
    # --- Auth gate: reject missing or non-admin user early ---
    user = get_current_user()
    if user is None:
        return jsonify({"status": "error", "message": "Authentication required"}), 401
    if user.role != "admin":
        return jsonify({"status": "error", "message": "Admin access required"}), 403

    # --- Payload extraction ---
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400

    name = body.get("name")
    price = body.get("price")
    stock = body.get("stock")

    if not name or price is None or stock is None:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    # --- Create and persist ---
    from app import db
    product = Product(name=name, price=float(price), stock=int(stock))
    db.session.add(product)
    db.session.commit()

    return jsonify({
        "status": "ok",
        "data": _product_to_dict(product),
    }), 201
