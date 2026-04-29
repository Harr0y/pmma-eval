"""
T2 Order System — Order Routes (Gen 1 Sample 1)

Implementation strategy: data-driven state machine with dedicated inventory helpers.

Key design decisions:
1. State transitions are defined in a dict (ALLOWED_TRANSITIONS) rather than
   scattered across if/elif chains. This makes the valid state graph explicit
   and easy to audit. The transition handler returns (new_status, handler_fn)
   where handler_fn is an optional side-effect callback (e.g. stock deduction,
   stock restoration, timestamp recording).

2. Inventory operations (deduct / restore) are encapsulated in standalone
   helper functions that iterate over OrderItem rows. This keeps the route
   handlers thin and makes the stock logic testable in isolation.

3. Serialization uses dedicated _serialize_xxx helpers for Order, OrderItem,
   and PaymentRequest. Each helper knows how to handle datetime fields via
   _dt_to_str, keeping the conversion logic in a single place.

4. Validation follows a fail-fast, layered approach: parse body -> check types
   -> check required fields -> check business rules (product existence, stock).
   No DB writes happen until all validation passes.

5. Idempotency is handled by checking PaymentRequest.idempotency_key before
   processing. If a matching key exists, the cached order status is returned
   without re-executing payment logic.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime
from flask import Blueprint, request, jsonify
from app import db
from models import Order, OrderItem, PaymentRequest, Product

order_bp = Blueprint('order_bp', __name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maps (current_status, action) -> (new_status, side_effect_fn | None)
# side_effect_fn signature: fn(order, items)
# If no side_effect is needed, use None.
ALLOWED_TRANSITIONS = {
    ('pending', 'pay'):     ('paid',     '_on_pay'),
    ('paid',    'ship'):    ('shipped',  '_on_ship'),
    ('shipped', 'deliver'): ('delivered', '_on_deliver'),
    ('pending', 'cancel'):  ('cancelled', '_on_cancel_pending'),
    ('paid',    'cancel'):  ('cancelled', '_on_cancel_paid'),
}

STATUS_TIMESTAMP_FIELD = {
    'paid':     'paid_at',
    'shipped':  'shipped_at',
    'delivered': 'delivered_at',
    'cancelled': 'cancelled_at',
}


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _dt_to_str(dt):
    """Convert a datetime to ISO string, or return None."""
    return dt.isoformat() if dt is not None else None


def _serialize_order(order, include_items=False):
    """Convert an Order ORM object to a plain dict."""
    data = {
        'id': order.id,
        'user_id': order.user_id,
        'status': order.status,
        'total_amount': order.total_amount,
        'created_at': _dt_to_str(order.created_at),
    }
    if include_items:
        data['items'] = [_serialize_order_item(item) for item in order.items]
    return data


def _serialize_order_item(item):
    """Convert an OrderItem ORM object to a plain dict."""
    return {
        'id': item.id,
        'product_id': item.product_id,
        'quantity': item.quantity,
        'unit_price': item.unit_price,
    }


# ---------------------------------------------------------------------------
# Inventory helpers
# ---------------------------------------------------------------------------

def _deduct_stock(order):
    """Deduct stock for all items in the order. Called once at payment time."""
    for item in order.items:
        product = Product.query.get(item.product_id)
        if product is not None:
            product.stock -= item.quantity


def _restore_stock(order):
    """Restore stock for all items in the order. Called when cancelling a paid order."""
    for item in order.items:
        product = Product.query.get(item.product_id)
        if product is not None:
            product.stock += item.quantity


# ---------------------------------------------------------------------------
# State machine side-effect handlers
# ---------------------------------------------------------------------------

def _on_pay(order, items):
    """Side effects for pending -> paid: deduct stock, record timestamp."""
    _deduct_stock(order)
    order.paid_at = datetime.utcnow()


def _on_ship(order, items):
    """Side effects for paid -> shipped: record timestamp."""
    order.shipped_at = datetime.utcnow()


def _on_deliver(order, items):
    """Side effects for shipped -> delivered: record timestamp."""
    order.delivered_at = datetime.utcnow()


def _on_cancel_pending(order, items):
    """Side effects for pending -> cancelled: record timestamp only (no stock change)."""
    order.cancelled_at = datetime.utcnow()


def _on_cancel_paid(order, items):
    """Side effects for paid -> cancelled: restore stock, record timestamp."""
    _restore_stock(order)
    order.cancelled_at = datetime.utcnow()


# Map from handler name string to actual function (used by the transition engine).
_SIDE_EFFECT_REGISTRY = {
    '_on_pay':              _on_pay,
    '_on_ship':             _on_ship,
    '_on_deliver':          _on_deliver,
    '_on_cancel_pending':   _on_cancel_pending,
    '_on_cancel_paid':      _on_cancel_paid,
}


def _execute_transition(order, action):
    """
    Attempt to transition an order's state.

    Returns (new_status, side_effect_fn) on success.
    Returns None if the transition is not allowed.
    """
    key = (order.status, action)
    entry = ALLOWED_TRANSITIONS.get(key)
    if entry is None:
        return None
    new_status, handler_name = entry
    side_effect_fn = _SIDE_EFFECT_REGISTRY.get(handler_name)
    return (new_status, side_effect_fn)


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _ok(data, status_code=200):
    return jsonify({'status': 'ok', 'data': data}), status_code


def _error(message, status_code=400):
    return jsonify({'status': 'error', 'message': message}), status_code


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order with items."""
    body = request.get_json(silent=True)

    # Layer 1: body must be a dict
    if not isinstance(body, dict):
        return _error('Request body must be a JSON object')

    # Layer 2: required top-level fields
    user_id = body.get('user_id')
    items = body.get('items')

    if user_id is None:
        return _error('Missing required field: user_id')
    if not isinstance(user_id, str) or not user_id.strip():
        return _error('"user_id" must be a non-empty string')

    if items is None:
        return _error('Missing required field: items')
    if not isinstance(items, list) or len(items) == 0:
        return _error('"items" must be a non-empty list')

    # Layer 3: validate each item
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            return _error(f'Item at index {idx} must be a JSON object')
        if 'product_id' not in item or 'quantity' not in item:
            return _error(f'Item at index {idx} must have "product_id" and "quantity"')
        if not isinstance(item['product_id'], int) or item['product_id'] < 1:
            return _error(f'Item at index {idx}: "product_id" must be a positive integer')
        if not isinstance(item['quantity'], int) or item['quantity'] < 1:
            return _error(f'Item at index {idx}: "quantity" must be a positive integer')

    # Layer 4: business rules -- check product existence and stock
    product_map = {}  # product_id -> Product
    for item in items:
        pid = item['product_id']
        if pid in product_map:
            continue  # already validated
        product = Product.query.get(pid)
        if product is None:
            return _error(f'Product with id {pid} not found')
        product_map[pid] = product

    # Aggregate quantities per product for stock check
    from collections import Counter
    qty_per_product = Counter()
    for item in items:
        qty_per_product[item['product_id']] += item['quantity']

    for pid, total_qty in qty_per_product.items():
        product = product_map[pid]
        if product.stock < total_qty:
            return _error(
                f'Insufficient stock for product {pid}: '
                f'need {total_qty}, have {product.stock}'
            )

    # All validation passed -- create order and items
    order = Order(user_id=user_id.strip(), status='pending', total_amount=0.0)
    db.session.add(order)
    db.session.flush()  # get order.id without committing

    total_amount = 0.0
    for item in items:
        product = product_map[item['product_id']]
        order_item = OrderItem(
            order_id=order.id,
            product_id=item['product_id'],
            quantity=item['quantity'],
            unit_price=product.price,
        )
        db.session.add(order_item)
        total_amount += product.price * item['quantity']

    order.total_amount = total_amount
    db.session.commit()

    return _ok(_serialize_order(order), status_code=201)


@order_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    """Get a single order with its items."""
    order = Order.query.get(order_id)
    if order is None:
        return _error(f'Order with id {order_id} not found', status_code=404)

    return _ok(_serialize_order(order, include_items=True))


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders, optionally filtered by user_id and/or status."""
    query = Order.query

    user_id = request.args.get('user_id')
    status = request.args.get('status')

    if user_id is not None:
        query = query.filter(Order.user_id == user_id)
    if status is not None:
        query = query.filter(Order.status == status)

    orders = query.order_by(Order.id.asc()).all()
    return _ok([_serialize_order(o) for o in orders])


@order_bp.route('/orders/<int:order_id>/pay', methods=['POST'])
def pay_order(order_id):
    """Pay for an order (pending -> paid). Requires Idempotency-Key header."""
    order = Order.query.get(order_id)
    if order is None:
        return _error(f'Order with id {order_id} not found', status_code=404)

    # Require Idempotency-Key header
    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return _error('Missing required header: Idempotency-Key')

    # Check for existing payment request with this key (idempotency)
    existing = PaymentRequest.query.filter_by(
        idempotency_key=idempotency_key
    ).first()

    if existing is not None:
        # Idempotent: return the current state of the associated order
        return _ok(_serialize_order(order))

    # Attempt state transition
    result = _execute_transition(order, 'pay')
    if result is None:
        return _error(
            f'Cannot pay order in status "{order.status}"',
            status_code=409,
        )

    new_status, side_effect_fn = result
    order.status = new_status
    if side_effect_fn is not None:
        side_effect_fn(order, order.items)

    # Record the payment request
    payment = PaymentRequest(
        order_id=order.id,
        idempotency_key=idempotency_key,
        status='completed',
    )
    db.session.add(payment)
    db.session.commit()

    return _ok(_serialize_order(order))


@order_bp.route('/orders/<int:order_id>/ship', methods=['POST'])
def ship_order(order_id):
    """Ship an order (paid -> shipped)."""
    order = Order.query.get(order_id)
    if order is None:
        return _error(f'Order with id {order_id} not found', status_code=404)

    result = _execute_transition(order, 'ship')
    if result is None:
        return _error(
            f'Cannot ship order in status "{order.status}"',
            status_code=409,
        )

    new_status, side_effect_fn = result
    order.status = new_status
    if side_effect_fn is not None:
        side_effect_fn(order, order.items)

    db.session.commit()
    return _ok(_serialize_order(order))


@order_bp.route('/orders/<int:order_id>/deliver', methods=['POST'])
def deliver_order(order_id):
    """Deliver an order (shipped -> delivered)."""
    order = Order.query.get(order_id)
    if order is None:
        return _error(f'Order with id {order_id} not found', status_code=404)

    result = _execute_transition(order, 'deliver')
    if result is None:
        return _error(
            f'Cannot deliver order in status "{order.status}"',
            status_code=409,
        )

    new_status, side_effect_fn = result
    order.status = new_status
    if side_effect_fn is not None:
        side_effect_fn(order, order.items)

    db.session.commit()
    return _ok(_serialize_order(order))


@order_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    """Cancel an order (pending/paid -> cancelled)."""
    order = Order.query.get(order_id)
    if order is None:
        return _error(f'Order with id {order_id} not found', status_code=404)

    result = _execute_transition(order, 'cancel')
    if result is None:
        return _error(
            f'Cannot cancel order in status "{order.status}"',
            status_code=409,
        )

    new_status, side_effect_fn = result
    order.status = new_status
    if side_effect_fn is not None:
        side_effect_fn(order, order.items)

    db.session.commit()
    return _ok(_serialize_order(order))
