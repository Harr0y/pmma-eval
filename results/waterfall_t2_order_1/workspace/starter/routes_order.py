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

from datetime import datetime

from flask import Blueprint, request, jsonify

from app import db
from models import Order, OrderItem, PaymentRequest, Product

order_bp = Blueprint('order_bp', __name__)


# ---------------------------------------------------------------------------
# Design spec 3.1 — State machine transition matrix
# ---------------------------------------------------------------------------

VALID_TRANSITIONS = {
    'pending':   {'pay', 'cancel'},
    'paid':      {'ship', 'cancel'},
    'shipped':   {'deliver'},
    'delivered': set(),
    'cancelled': set(),
}


def validate_transition(current_status, action):
    """Check whether *action* is a legal transition from *current_status*.

    Spec: design.md section 3.1 — returns True if legal, False otherwise.
    """
    return action in VALID_TRANSITIONS.get(current_status, set())


# ---------------------------------------------------------------------------
# Design spec section 4 — Serialization helpers
# ---------------------------------------------------------------------------

def serialize_order(order, include_items=False):
    """Serialize an Order model instance to a plain dict.

    Spec: design.md section 4 — serialize_order(order, include_items=False).
    When include_items is True, include the list of OrderItem dicts.
    """
    data = {
        "id": order.id,
        "user_id": order.user_id,
        "status": order.status,
        "total_amount": order.total_amount,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }
    if include_items:
        data["items"] = [
            {
                "id": item.id,
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
            }
            for item in order.items
        ]
    return data


# ---------------------------------------------------------------------------
# Design spec 2.2 — POST /orders  (create order)
# ---------------------------------------------------------------------------

@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order.

    Spec: design.md section 2.2 — POST /orders.
    1. Defensive check: request.json is None -> 400
    2. Validate user_id exists and is non-empty string
    3. Validate items exists and is a non-empty list
    4. For each item: validate product exists and stock >= quantity
    5. Compute total_amount = sum(product.price * quantity)
    6. Create Order (status='pending') and OrderItem records
    7. Return 201 + serialized order (without items)
    """
    # 1. Defensive check
    if request.json is None:
        return jsonify({
            "status": "error",
            "message": "Request body must be JSON",
        }), 400

    data = request.json

    # 2. Validate user_id
    user_id = data.get('user_id')
    if not user_id or not isinstance(user_id, str) or user_id.strip() == '':
        return jsonify({
            "status": "error",
            "message": "Missing required field: user_id",
        }), 400

    # 3. Validate items
    items = data.get('items')
    if not items or not isinstance(items, list) or len(items) == 0:
        return jsonify({
            "status": "error",
            "message": "Items list must not be empty",
        }), 400

    # 4-5. Validate products and compute total
    total_amount = 0.0
    validated_items = []  # list of (product, quantity) tuples

    for item in items:
        product_id = item.get('product_id')
        quantity = item.get('quantity')

        if product_id is None or quantity is None:
            return jsonify({
                "status": "error",
                "message": "Each item must have product_id and quantity",
            }), 400

        product = db.session.get(Product, product_id)
        if product is None:
            return jsonify({
                "status": "error",
                "message": f"Product not found: id={product_id}",
            }), 400

        if product.stock < quantity:
            return jsonify({
                "status": "error",
                "message": f"Insufficient stock for product id={product_id}",
            }), 400

        total_amount += product.price * quantity
        validated_items.append((product, quantity))

    # 6. Create Order + OrderItem records
    order = Order(
        user_id=user_id,
        status='pending',
        total_amount=total_amount,
    )
    db.session.add(order)
    db.session.flush()  # get order.id before creating OrderItems

    for product, quantity in validated_items:
        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=product.price,
        )
        db.session.add(order_item)

    db.session.commit()

    return jsonify({
        "status": "ok",
        "data": serialize_order(order),
    }), 201


# ---------------------------------------------------------------------------
# Design spec 2.2 — GET /orders/<id>  (order detail)
# ---------------------------------------------------------------------------

@order_bp.route('/orders/<int:id>', methods=['GET'])
def get_order(id):
    """Get a single order by ID, including its items.

    Spec: design.md section 2.2 — GET /orders/<id>.
    Returns 404 if order does not exist.
    """
    order = db.session.get(Order, id)
    if order is None:
        return jsonify({
            "status": "error",
            "message": "Order not found",
        }), 404

    return jsonify({
        "status": "ok",
        "data": serialize_order(order, include_items=True),
    }), 200


# ---------------------------------------------------------------------------
# Design spec 2.2 — GET /orders  (list/filter orders)
# ---------------------------------------------------------------------------

@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders, optionally filtered by user_id and/or status.

    Spec: design.md section 2.2 — GET /orders.
    Returns 200 with {"status": "ok", "data": [...]}.
    When no orders match, data is an empty list [].
    """
    query = Order.query

    user_id = request.args.get('user_id')
    if user_id is not None:
        query = query.filter_by(user_id=user_id)

    status = request.args.get('status')
    if status is not None:
        query = query.filter_by(status=status)

    orders = query.all()
    return jsonify({
        "status": "ok",
        "data": [serialize_order(o) for o in orders],
    }), 200


# ---------------------------------------------------------------------------
# Design spec 2.2 — POST /orders/<id>/pay  (idempotent payment)
# ---------------------------------------------------------------------------

@order_bp.route('/orders/<int:id>/pay', methods=['POST'])
def pay_order(id):
    """Pay for an order (pending -> paid) with idempotency support.

    Spec: design.md section 2.2 — POST /orders/<id>/pay.
    Flow:
    1. Get Idempotency-Key header (missing -> 400)
    2. Query Order by id (not found -> 404)
    3. Check idempotency: PaymentRequest where idempotency_key=key AND order_id=id
       -> already exists: return current order state (no re-processing)
    4. Validate transition with validate_transition(order.status, 'pay') -> 409
    5. Deduct stock for each OrderItem
    6. Update order: status='paid', paid_at=now
    7. Create PaymentRequest(status='paid')
    8. db.session.commit()
    9. Return 200
    """
    # 1. Get Idempotency-Key header
    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify({
            "status": "error",
            "message": "Idempotency-Key header is required",
        }), 400

    # 2. Query Order
    order = db.session.get(Order, id)
    if order is None:
        return jsonify({
            "status": "error",
            "message": "Order not found",
        }), 404

    # 3. Check idempotency: idempotency_key + order_id joint query
    existing_payment = PaymentRequest.query.filter_by(
        idempotency_key=idempotency_key,
        order_id=id,
    ).first()

    if existing_payment is not None:
        # Idempotent hit — return current order state without re-processing
        return jsonify({
            "status": "ok",
            "data": serialize_order(order),
        }), 200

    # 4. Validate state transition
    if not validate_transition(order.status, 'pay'):
        current = order.status
        target = 'paid'
        return jsonify({
            "status": "error",
            "message": f"Cannot transition from {current} to {target}",
        }), 409

    # 5. Deduct stock
    for item in order.items:
        product = db.session.get(Product, item.product_id)
        product.stock -= item.quantity

    # 6. Update order
    order.status = 'paid'
    order.paid_at = datetime.utcnow()

    # 7. Create PaymentRequest (status='paid' directly)
    payment = PaymentRequest(
        order_id=order.id,
        idempotency_key=idempotency_key,
        status='paid',
    )
    db.session.add(payment)

    # 8. Commit
    db.session.commit()

    # 9. Return
    return jsonify({
        "status": "ok",
        "data": serialize_order(order),
    }), 200


# ---------------------------------------------------------------------------
# Design spec 2.2 — POST /orders/<id>/ship  (ship order)
# ---------------------------------------------------------------------------

@order_bp.route('/orders/<int:id>/ship', methods=['POST'])
def ship_order(id):
    """Ship an order (paid -> shipped).

    Spec: design.md section 2.2 — POST /orders/<id>/ship.
    """
    order = db.session.get(Order, id)
    if order is None:
        return jsonify({
            "status": "error",
            "message": "Order not found",
        }), 404

    if not validate_transition(order.status, 'ship'):
        current = order.status
        target = 'shipped'
        return jsonify({
            "status": "error",
            "message": f"Cannot transition from {current} to {target}",
        }), 409

    order.status = 'shipped'
    order.shipped_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "status": "ok",
        "data": serialize_order(order),
    }), 200


# ---------------------------------------------------------------------------
# Design spec 2.2 — POST /orders/<id>/deliver  (deliver order)
# ---------------------------------------------------------------------------

@order_bp.route('/orders/<int:id>/deliver', methods=['POST'])
def deliver_order(id):
    """Deliver an order (shipped -> delivered).

    Spec: design.md section 2.2 — POST /orders/<id>/deliver.
    """
    order = db.session.get(Order, id)
    if order is None:
        return jsonify({
            "status": "error",
            "message": "Order not found",
        }), 404

    if not validate_transition(order.status, 'deliver'):
        current = order.status
        target = 'delivered'
        return jsonify({
            "status": "error",
            "message": f"Cannot transition from {current} to {target}",
        }), 409

    order.status = 'delivered'
    order.delivered_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "status": "ok",
        "data": serialize_order(order),
    }), 200


# ---------------------------------------------------------------------------
# Design spec 2.2 — POST /orders/<id>/cancel  (cancel order)
# ---------------------------------------------------------------------------

@order_bp.route('/orders/<int:id>/cancel', methods=['POST'])
def cancel_order(id):
    """Cancel an order (pending/paid -> cancelled).

    Spec: design.md section 2.2 — POST /orders/<id>/cancel.
    If the order was in 'paid' state, restore product stock.
    """
    order = db.session.get(Order, id)
    if order is None:
        return jsonify({
            "status": "error",
            "message": "Order not found",
        }), 404

    if not validate_transition(order.status, 'cancel'):
        current = order.status
        target = 'cancelled'
        return jsonify({
            "status": "error",
            "message": f"Cannot transition from {current} to {target}",
        }), 409

    # If order was paid, restore stock
    if order.status == 'paid':
        for item in order.items:
            product = db.session.get(Product, item.product_id)
            product.stock += item.quantity

    order.status = 'cancelled'
    order.cancelled_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "status": "ok",
        "data": serialize_order(order),
    }), 200
