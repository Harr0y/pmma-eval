"""
T2 Order System — Order Routes

Implement order CRUD, state machine, and payment with idempotency.
Register as a Flask Blueprint named 'order_bp'.

Order state machine:
  pending -> paid -> shipped -> delivered
  pending/paid -> cancelled

Requirements:
- POST /orders -> Create order
  Request: {"user_id": str, "items": [{"product_id": int, "quantity": int}, ...]}
  Response: {"status": "ok", "data": {"id": int, "user_id": str, "status": "pending",
            "total_amount": float, "created_at": str}}
  - Validates all products exist and stock is available
  - Creates OrderItem records for each product
  - total_amount = sum of (product.price * quantity) for all items
Errors: 400 if invalid data, product not found, or insufficient stock

- GET /orders/<id> -> Get order with items
  Response: {"status": "ok", "data": {"id": int, "user_id": str, "status": str,
            "total_amount": float, "created_at": str,
            "items": [{"id": int, "product_id": int, "quantity": int, "unit_price": float}, ...]}}
  Errors: 404 if not found

- GET /orders -> List orders, filter by user_id and/or status
  Query params: user_id, status
  Response: {"status": "ok", "data": [...]}

- POST /orders/<id>/pay -> Pay for order (pending -> paid)
  Header: Idempotency-Key (required)
  - Deducts stock from products
  - Records PaymentRequest for idempotency
  - Duplicate Idempotency-Key returns same result without re-processing
  Errors: 404 if order not found, 400 if no key, 409 if invalid state transition

- POST /orders/<id>/ship -> Ship order (paid -> shipped)
  Errors: 404 if not found, 409 if invalid state

- POST /orders/<id>/deliver -> Deliver order (shipped -> delivered)
  Errors: 404 if not found, 409 if invalid state

- POST /orders/<id>/cancel -> Cancel order (pending/paid -> cancelled)
  - Restores product stock if order was paid
  Errors: 404 if not found, 409 if invalid state

IMPORTANT: This module works with models.py (Order, OrderItem, PaymentRequest, Product)
and routes_product.py. Stock deduction happens at payment time, not order creation.
"""

from collections import defaultdict
from datetime import datetime
from flask import Blueprint, request, jsonify

from models import Product, Order, OrderItem, PaymentRequest
from app import db

order_bp = Blueprint('order_bp', __name__)


# ---------------------------------------------------------------------------
# Helper functions (design.md section 3.5, 7.1)
# ---------------------------------------------------------------------------

def error_response(message, status_code):
    """Return a unified error response."""
    return jsonify({"status": "error", "message": message}), status_code


def serialize_order(o, include_items=False):
    """Serialize an Order model instance to a dict.

    Args:
        o: Order model instance.
        include_items: If True, include the items list in the output.
    """
    data = {
        "id": o.id,
        "user_id": o.user_id,
        "status": o.status,
        "total_amount": o.total_amount,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }
    if include_items:
        data["items"] = [
            {
                "id": i.id,
                "product_id": i.product_id,
                "quantity": i.quantity,
                "unit_price": i.unit_price,
            }
            for i in o.items
        ]
    return data


# ---------------------------------------------------------------------------
# ATU-004: Order CRUD endpoints
# ---------------------------------------------------------------------------

@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order.

    Request body: {"user_id": str, "items": [{"product_id": int, "quantity": int}, ...]}
    - Validates items is non-empty.
    - Validates all product_ids exist.
    - Merges quantities for duplicate product_ids and checks stock.
    - Computes total_amount = sum(product.price * quantity) per item.
    - Creates Order + OrderItem records. Does NOT deduct stock.
    Returns 201 on success, 400 on validation error.
    """
    data = request.get_json(silent=True)
    if data is None:
        return error_response("Request body must be valid JSON", 400)

    user_id = data.get('user_id')
    items = data.get('items')

    if not user_id:
        return error_response("Missing required field: user_id", 400)

    if not items or not isinstance(items, list) or len(items) == 0:
        return error_response("items must be a non-empty list", 400)

    # Validate all items have product_id and quantity
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            return error_response(f"items[{idx}] must be an object", 400)
        if item.get('product_id') is None:
            return error_response(f"items[{idx}] missing product_id", 400)
        if item.get('quantity') is None or int(item['quantity']) <= 0:
            return error_response(f"items[{idx}] must have a positive quantity", 400)

    # Step 2: Validate all products exist
    products = {}
    for item in items:
        pid = int(item['product_id'])
        if pid in products:
            continue
        product = Product.query.get(pid)
        if product is None:
            return error_response(f"Product {pid} not found", 400)
        products[pid] = product

    # Step 3: Merge quantities for duplicate product_ids
    merged = defaultdict(int)
    for item in items:
        merged[int(item['product_id'])] += int(item['quantity'])

    # Step 4: Check stock for merged quantities
    for pid, total_qty in merged.items():
        product = products[pid]
        if product.stock < total_qty:
            return error_response(
                f"Insufficient stock for product {pid}: need {total_qty}, have {product.stock}",
                400,
            )

    # Step 5: Compute total_amount = sum(product.price * item.quantity) per item
    total_amount = 0.0
    for item in items:
        pid = int(item['product_id'])
        qty = int(item['quantity'])
        total_amount += products[pid].price * qty

    # Step 6-7: Create Order and OrderItem records
    order = Order(user_id=user_id, status='pending', total_amount=total_amount)
    db.session.add(order)
    db.session.flush()  # Flush to get order.id before creating OrderItems

    for item in items:
        pid = int(item['product_id'])
        qty = int(item['quantity'])
        order_item = OrderItem(
            order_id=order.id,
            product_id=pid,
            quantity=qty,
            unit_price=products[pid].price,
        )
        db.session.add(order_item)

    # Step 8: Commit
    db.session.commit()

    # Step 9: Return 201 + order data (without items)
    return jsonify({"status": "ok", "data": serialize_order(order, include_items=False)}), 201


@order_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    """Get order details including items.

    Returns 200 with order data + items list, or 404 if not found.
    """
    order = Order.query.get(order_id)
    if order is None:
        return error_response("Order not found", 404)

    return jsonify({"status": "ok", "data": serialize_order(order, include_items=True)}), 200


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders with optional filtering by user_id and/or status.

    Query params: user_id (optional), status (optional).
    Response data does NOT include items details.
    Returns 200 with a list of order dicts.
    """
    query = Order.query

    user_id = request.args.get('user_id')
    status = request.args.get('status')

    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    if status is not None:
        query = query.filter_by(status=status)

    orders = query.all()
    return jsonify({
        "status": "ok",
        "data": [serialize_order(o, include_items=False) for o in orders],
    }), 200


# ---------------------------------------------------------------------------
# ATU-005: Pay endpoint — POST /orders/<id>/pay
# Design spec: design.md section 2.2 (pay endpoint), 3.2 (payment flow), 4 (idempotency)
# ---------------------------------------------------------------------------

@order_bp.route('/orders/<int:order_id>/pay', methods=['POST'])
def pay_order(order_id):
    """Pay for an order (pending -> paid).

    Header: Idempotency-Key (required).

    Algorithm (design.md section 3.2):
      1. Get Idempotency-Key from request.headers — missing -> 400
      2. Query Order.query.get(id) — not found -> 404
      3. Query PaymentRequest by idempotency_key:
         - exists -> idempotent return 200 + current order data (no stock deduction)
         - not exists -> continue
      4. Status check: order.status == 'pending' — not satisfied -> 409
      5. Create PaymentRequest(order_id=order.id, idempotency_key=key)
      6. Deduct stock: product.stock -= item.quantity for each order item
      7. Update order: status='paid', paid_at=datetime.utcnow()
      8. db.session.commit()
      9. Return 200 + order data

    Errors: 400 (no key), 404 (order not found), 409 (invalid state transition).
    """
    # Step 1: Get Idempotency-Key from request headers
    key = request.headers.get('Idempotency-Key')
    if not key:
        return error_response("Missing required header: Idempotency-Key", 400)

    # Step 2: Query order
    order = Order.query.get(order_id)
    if order is None:
        return error_response("Order not found", 404)

    # Step 3: Check for existing PaymentRequest (idempotency)
    existing = PaymentRequest.query.filter_by(idempotency_key=key).first()
    if existing is not None:
        # Idempotent return: return current order data without re-processing
        return jsonify({"status": "ok", "data": serialize_order(order, include_items=False)}), 200

    # Step 4: Status check — only 'pending' can be paid
    if order.status != 'pending':
        return error_response(
            f"Invalid state transition: cannot pay order in '{order.status}' state",
            409,
        )

    # Step 5: Create PaymentRequest record
    payment_request = PaymentRequest(order_id=order.id, idempotency_key=key)
    db.session.add(payment_request)

    # Step 6: Deduct stock for each order item
    for item in order.items:
        product = Product.query.get(item.product_id)
        if product is not None:
            product.stock -= item.quantity

    # Step 7: Update order status and paid_at timestamp
    order.status = 'paid'
    order.paid_at = datetime.utcnow()

    # Step 8: Commit all changes
    db.session.commit()

    # Step 9: Return 200 + order data
    return jsonify({"status": "ok", "data": serialize_order(order, include_items=False)}), 200


# ---------------------------------------------------------------------------
# ATU-006: State machine — ship, deliver, cancel endpoints
# Design spec: design.md section 2.2 (ship/deliver/cancel), 3.3 (state
# transition validation), 3.4 (cancel with stock rollback)
# ---------------------------------------------------------------------------

VALID_TRANSITIONS = {
    'pending': {'pay', 'cancel'},
    'paid': {'ship', 'cancel'},
    'shipped': {'deliver'},
    'delivered': set(),
    'cancelled': set(),
}


def check_transition(order, action):
    """Validate that the given action is allowed for the order's current status.

    Args:
        order: Order model instance.
        action: The action to perform (e.g. 'ship', 'deliver', 'cancel').

    Returns:
        True if the transition is valid, False otherwise.
    """
    valid_actions = VALID_TRANSITIONS.get(order.status, set())
    return action in valid_actions


@order_bp.route('/orders/<int:order_id>/ship', methods=['POST'])
def ship_order(order_id):
    """Ship an order (paid -> shipped).

    Algorithm:
      1. Query Order.query.get(id) — not found -> 404
      2. Validate state transition via check_transition(order, 'ship')
         — invalid -> 409
      3. Set order.shipped_at = datetime.utcnow()
      4. Update order.status = 'shipped'
      5. db.session.commit()
      6. Return 200 + order data

    Errors: 404 if order not found, 409 if invalid state transition.
    """
    order = Order.query.get(order_id)
    if order is None:
        return error_response("Order not found", 404)

    if not check_transition(order, 'ship'):
        return error_response(
            f"Invalid state transition: cannot ship order in '{order.status}' state",
            409,
        )

    order.shipped_at = datetime.utcnow()
    order.status = 'shipped'
    db.session.commit()

    return jsonify({"status": "ok", "data": serialize_order(order, include_items=False)}), 200


@order_bp.route('/orders/<int:order_id>/deliver', methods=['POST'])
def deliver_order(order_id):
    """Deliver an order (shipped -> delivered).

    Algorithm:
      1. Query Order.query.get(id) — not found -> 404
      2. Validate state transition via check_transition(order, 'deliver')
         — invalid -> 409
      3. Set order.delivered_at = datetime.utcnow()
      4. Update order.status = 'delivered'
      5. db.session.commit()
      6. Return 200 + order data

    Errors: 404 if order not found, 409 if invalid state transition.
    """
    order = Order.query.get(order_id)
    if order is None:
        return error_response("Order not found", 404)

    if not check_transition(order, 'deliver'):
        return error_response(
            f"Invalid state transition: cannot deliver order in '{order.status}' state",
            409,
        )

    order.delivered_at = datetime.utcnow()
    order.status = 'delivered'
    db.session.commit()

    return jsonify({"status": "ok", "data": serialize_order(order, include_items=False)}), 200


@order_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    """Cancel an order (pending/paid -> cancelled).

    Algorithm (design.md section 3.4):
      1. Query Order.query.get(id) — not found -> 404
      2. Validate state transition via check_transition(order, 'cancel')
         — invalid -> 409
      3. If order.status == 'paid':
         - Restore stock: iterate order.items, product.stock += item.quantity
      4. Set order.cancelled_at = datetime.utcnow()
      5. Update order.status = 'cancelled'
      6. db.session.commit()
      7. Return 200 + order data

    Errors: 404 if order not found, 409 if invalid state transition.
    """
    order = Order.query.get(order_id)
    if order is None:
        return error_response("Order not found", 404)

    if not check_transition(order, 'cancel'):
        return error_response(
            f"Invalid state transition: cannot cancel order in '{order.status}' state",
            409,
        )

    # Roll back stock if order was paid (design.md section 3.4)
    if order.status == 'paid':
        for item in order.items:
            product = Product.query.get(item.product_id)
            if product is not None:
                product.stock += item.quantity

    order.cancelled_at = datetime.utcnow()
    order.status = 'cancelled'
    db.session.commit()

    return jsonify({"status": "ok", "data": serialize_order(order, include_items=False)}), 200
