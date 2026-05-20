"""
routes_order_sample1.py — Order routes with transition-map state machine (Gen 1 Sample 1)

Mutation strategy:
- Transition-map dictionary for state machine (no if-elif chains)
- Standalone helper functions for stock operations (deduct_stock, restore_stock)
- Unified serialization helpers (_serialize_order, _serialize_order_item, _serialize_orders)
- Class-method-free, pure-functional approach
- datetime.utcnow() for state change timestamps

State transitions map:
    {
        'pay':     {'pending': 'paid'},
        'ship':    {'paid': 'shipped'},
        'deliver': {'shipped': 'delivered'},
        'cancel':  {'pending': 'cancelled', 'paid': 'cancelled'},
    }
"""

from datetime import datetime
from flask import Blueprint, request, jsonify
from sqlalchemy import and_

from app import db
from models import Product, Order, OrderItem, PaymentRequest

order_bp = Blueprint('order_bp', __name__)

# ── State Machine ──────────────────────────────────────────────

# Each key is an action name, value maps *current* status to *next* status.
TRANSITIONS = {
    'pay':     {'pending': 'paid'},
    'ship':    {'paid': 'shipped'},
    'deliver': {'shipped': 'delivered'},
    'cancel':  {'pending': 'cancelled', 'paid': 'cancelled'},
}


def _resolve_transition(action, current_status):
    """Look up the next status for a given action and current status.

    Returns the target status string, or None if the transition is illegal.
    """
    action_map = TRANSITIONS.get(action)
    if action_map is None:
        return None
    return action_map.get(current_status)


# ── Timestamp helpers ──────────────────────────────────────────

# Map each target status to the column that should receive a timestamp.
_TIMESTAMP_COLUMNS = {
    'paid': 'paid_at',
    'shipped': 'shipped_at',
    'delivered': 'delivered_at',
    'cancelled': 'cancelled_at',
}


def _stamp_transition(order, target_status):
    """Set the appropriate timestamp column for a state transition."""
    col_name = _TIMESTAMP_COLUMNS.get(target_status)
    if col_name:
        setattr(order, col_name, datetime.utcnow())


# ── Inventory helpers ──────────────────────────────────────────

def deduct_stock(order):
    """Deduct product stock for every item in the order.

    Call this exactly once per payment (idempotency guard upstream).
    """
    for item in order.items:
        product = db.session.get(Product, item.product_id)
        product.stock -= item.quantity


def restore_stock(order):
    """Restore product stock for every item in a paid order.

    Used when cancelling a paid order to roll back the deduction.
    """
    for item in order.items:
        product = db.session.get(Product, item.product_id)
        product.stock += item.quantity


# ── Serialization helpers ──────────────────────────────────────

_ORDER_FIELDS = ('id', 'user_id', 'status', 'total_amount', 'created_at')
_ORDER_ITEM_FIELDS = ('id', 'product_id', 'quantity', 'unit_price')


def _serialize_order(order):
    """Serialize an Order ORM object to a plain dict."""
    return {
        key: getattr(order, key)
        for key in _ORDER_FIELDS
    }


def _serialize_order_with_items(order):
    """Serialize an Order with its nested items list."""
    data = _serialize_order(order)
    data['items'] = [
        {k: getattr(item, k) for k in _ORDER_ITEM_FIELDS}
        for item in order.items
    ]
    return data


def _serialize_orders(orders):
    """Serialize a list of Order objects."""
    return [_serialize_order(o) for o in orders]


def _success_response(data, status_code=200):
    """Build a standardized success JSON response."""
    return jsonify({"status": "ok", "data": data}), status_code


def _error_response(message, status_code=400):
    """Build a standardized error JSON response."""
    return jsonify({"status": "error", "message": message}), status_code


# ── Route handlers ─────────────────────────────────────────────

@order_bp.route('/orders', methods=['POST'])
def create_order():
    """POST /orders — Create a new order with items."""
    try:
        payload = request.get_json(silent=True)
        if payload is None:
            return _error_response("Request body must be valid JSON")

        user_id = payload.get('user_id')
        items_payload = payload.get('items')

        if not user_id:
            return _error_response("Missing required field: user_id")
        if not items_payload or not isinstance(items_payload, list):
            return _error_response("Missing or invalid field: items")

        # Validate products and calculate total
        order_items = []
        total_amount = 0.0

        for entry in items_payload:
            product_id = entry.get('product_id')
            quantity = entry.get('quantity')

            if product_id is None or quantity is None:
                return _error_response(
                    "Each item must have product_id and quantity"
                )

            product = db.session.get(Product, int(product_id))
            if product is None:
                return _error_response(
                    f"Product {product_id} not found"
                )

            if product.stock < int(quantity):
                return _error_response(
                    f"Insufficient stock for product {product_id}: "
                    f"need {quantity}, have {product.stock}"
                )

            order_items.append((product, int(quantity)))
            total_amount += product.price * int(quantity)

        # Create Order + OrderItems
        order = Order(
            user_id=user_id,
            status='pending',
            total_amount=total_amount,
        )
        db.session.add(order)
        db.session.flush()  # ensure order.id is assigned

        for product, qty in order_items:
            item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=qty,
                unit_price=product.price,
            )
            db.session.add(item)

        db.session.commit()
        return _success_response(_serialize_order(order), 201)

    except Exception as exc:
        db.session.rollback()
        return _error_response(str(exc))


@order_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    """GET /orders/<id> — Retrieve a single order with its items."""
    try:
        order = db.session.get(Order, order_id)
        if order is None:
            return _error_response(f"Order {order_id} not found", 404)

        return _success_response(_serialize_order_with_items(order))
    except Exception as exc:
        return _error_response(str(exc), 500)


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """GET /orders — List orders, optionally filtered by user_id and/or status."""
    try:
        filters = []
        user_id = request.args.get('user_id')
        status = request.args.get('status')

        if user_id is not None:
            filters.append(Order.user_id == user_id)
        if status is not None:
            filters.append(Order.status == status)

        query = Order.query
        if filters:
            query = query.filter(and_(*filters))

        orders = query.all()
        return _success_response(_serialize_orders(orders))
    except Exception as exc:
        return _error_response(str(exc), 500)


@order_bp.route('/orders/<int:order_id>/pay', methods=['POST'])
def pay_order(order_id):
    """POST /orders/<id>/pay — Pay for order (pending -> paid).

    Requires Idempotency-Key header. Duplicate keys return the same result
    without re-processing or re-deducting stock.
    """
    try:
        # Idempotency-Key is mandatory
        idempotency_key = request.headers.get('Idempotency-Key')
        if not idempotency_key:
            return _error_response("Missing required header: Idempotency-Key")

        order = db.session.get(Order, order_id)
        if order is None:
            return _error_response(f"Order {order_id} not found", 404)

        # Check for duplicate idempotency key
        existing = PaymentRequest.query.filter_by(
            idempotency_key=idempotency_key
        ).first()

        if existing is not None:
            # Idempotent return — return the current order state
            return _success_response(_serialize_order(order))

        # Resolve transition
        target = _resolve_transition('pay', order.status)
        if target is None:
            return _error_response(
                f"Cannot transition order {order_id} from '{order.status}' to 'paid'",
                409,
            )

        # Perform transition
        order.status = target
        _stamp_transition(order, target)
        deduct_stock(order)

        # Record payment request
        payment = PaymentRequest(
            order_id=order.id,
            idempotency_key=idempotency_key,
            status='completed',
        )
        db.session.add(payment)
        db.session.commit()

        return _success_response(_serialize_order(order))

    except Exception as exc:
        db.session.rollback()
        return _error_response(str(exc))


@order_bp.route('/orders/<int:order_id>/ship', methods=['POST'])
def ship_order(order_id):
    """POST /orders/<id>/ship — Ship order (paid -> shipped)."""
    try:
        order = db.session.get(Order, order_id)
        if order is None:
            return _error_response(f"Order {order_id} not found", 404)

        target = _resolve_transition('ship', order.status)
        if target is None:
            return _error_response(
                f"Cannot transition order {order_id} from '{order.status}' to 'shipped'",
                409,
            )

        order.status = target
        _stamp_transition(order, target)
        db.session.commit()

        return _success_response(_serialize_order(order))

    except Exception as exc:
        db.session.rollback()
        return _error_response(str(exc))


@order_bp.route('/orders/<int:order_id>/deliver', methods=['POST'])
def deliver_order(order_id):
    """POST /orders/<id>/deliver — Deliver order (shipped -> delivered)."""
    try:
        order = db.session.get(Order, order_id)
        if order is None:
            return _error_response(f"Order {order_id} not found", 404)

        target = _resolve_transition('deliver', order.status)
        if target is None:
            return _error_response(
                f"Cannot transition order {order_id} from '{order.status}' to 'delivered'",
                409,
            )

        order.status = target
        _stamp_transition(order, target)
        db.session.commit()

        return _success_response(_serialize_order(order))

    except Exception as exc:
        db.session.rollback()
        return _error_response(str(exc))


@order_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    """POST /orders/<id>/cancel — Cancel order (pending/paid -> cancelled).

    If the order was paid, product stock is restored.
    """
    try:
        order = db.session.get(Order, order_id)
        if order is None:
            return _error_response(f"Order {order_id} not found", 404)

        previous_status = order.status

        target = _resolve_transition('cancel', previous_status)
        if target is None:
            return _error_response(
                f"Cannot transition order {order_id} from '{previous_status}' to 'cancelled'",
                409,
            )

        order.status = target
        _stamp_transition(order, target)

        # If the order was paid, roll back stock deductions
        if previous_status == 'paid':
            restore_stock(order)

        db.session.commit()

        return _success_response(_serialize_order(order))

    except Exception as exc:
        db.session.rollback()
        return _error_response(str(exc))
