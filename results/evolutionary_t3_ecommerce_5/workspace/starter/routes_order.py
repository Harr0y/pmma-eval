"""
T3 E-commerce - Order Routes (Gen 1, Sample 1 — with Rate Limiting)

Implementation strategy:
- Inherited from ATU-002 Gen 2 Sample 3: pessimistic locking (SELECT FOR UPDATE),
  guard clause / early-return pattern, try/except/rollback transaction safety,
  _order_to_dict() serialization helper with origin field.
- Mutation: integrated rate limiting via middleware.check_rate_limit() and
  middleware.record_success(). Rate check is placed after auth gate, before
  any payload parsing or DB work — fail fast on rate-limited requests.
- Mutation: rate limit state recorded only on successful order creation (not
  on failed attempts), so stock-out errors don't consume the rate limit window.

Evolutionary notes:
- Inherited: pessimistic lock, _order_to_dict helper, guard clauses,
  try/except/rollback, origin field default 'web'.
- Mutation: two-phase rate limiting (check before, record after commit).
- Mutation: rate limit 429 returned as early as possible in the pipeline.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Blueprint, request, jsonify
from models import User, Product, Order
from middleware import get_current_user, get_rate_limiter

order_bp = Blueprint('order_bp', __name__)


def _order_to_dict(order):
    """Serialize an Order ORM object into a plain dict, including origin."""
    return {
        "id": order.id,
        "user_id": order.user_id,
        "product_id": order.product_id,
        "quantity": order.quantity,
        "total_price": order.total_price,
        "origin": order.origin,
    }


# ── POST /orders ──────────────────────────────────────────────
@order_bp.route('/orders', methods=['POST'])
def create_order():
    # --- Auth gate ---
    user = get_current_user()
    if user is None:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    # --- Rate limit gate (after auth, before any DB work) ---
    limiter = get_rate_limiter()
    if limiter.check_rate_limit(user.id):
        return jsonify({
            "status": "error",
            "message": "Rate limit exceeded: only 1 order per 10 seconds",
        }), 429

    # --- Payload extraction ---
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400

    product_id = body.get("product_id")
    quantity = body.get("quantity")

    if product_id is None or quantity is None:
        return jsonify({"status": "error", "message": "Missing product_id or quantity"}), 400

    try:
        quantity = int(quantity)
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Invalid quantity"}), 400

    if quantity <= 0:
        return jsonify({"status": "error", "message": "Quantity must be positive"}), 400

    # --- Origin field: default 'web', overrideable ---
    origin = body.get("origin", "web")

    # --- Atomic stock deduction + order creation in a single transaction ---
    from app import db

    try:
        # Lock the product row to prevent concurrent stock modifications
        product = (
            Product.query
            .filter_by(id=product_id)
            .with_for_update()
            .first()
        )

        if product is None:
            return jsonify({"status": "error", "message": "Product not found"}), 404

        if product.stock < quantity:
            return jsonify({"status": "error", "message": "Insufficient stock"}), 400

        # Deduct stock
        product.stock -= quantity

        # Create order
        total_price = product.price * quantity
        order = Order(
            user_id=user.id,
            product_id=product.id,
            quantity=quantity,
            total_price=total_price,
            origin=origin,
        )
        db.session.add(order)
        db.session.commit()

    except Exception:
        db.session.rollback()
        return jsonify({"status": "error", "message": "Internal server error"}), 500

    # --- Record successful order for rate limiting ---
    limiter.record_success(user.id)

    return jsonify({
        "status": "ok",
        "data": _order_to_dict(order),
    }), 201


# ── GET /orders ───────────────────────────────────────────────
@order_bp.route('/orders', methods=['GET'])
def list_orders():
    # --- Auth gate ---
    user = get_current_user()
    if user is None:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    # --- Query based on role ---
    if user.role == "admin":
        orders = Order.query.all()
    else:
        orders = Order.query.filter_by(user_id=user.id).all()

    return jsonify({
        "status": "ok",
        "data": [_order_to_dict(o) for o in orders],
    })
