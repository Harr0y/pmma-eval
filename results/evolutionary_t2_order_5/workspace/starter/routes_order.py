"""
T2 Order System - Order Routes (Sample 2: Serializer + bulk lookup + state-table pattern)

Design decisions (Gen-1 Sample 2 variant):
  - OrderSerializer / OrderItemSerializer classes centralise serialisation (one/many).
  - Product lookup uses dict-based batch fetch: collect all product_ids, query once,
    build a lookup dict.  This avoids N+1 queries when validating multi-item orders.
  - State transitions are driven by a STATE_TRANSITIONS table (dict of allowed
    {current: {action: next}}) instead of a chain of if/elif branches.
  - filter_by() with **kwargs for dynamic query construction on GET /orders.
  - Guard clauses throughout; no deep nesting.
  - Imports db from models.py (not app.py) to avoid circular imports.

Author: Gen-1 Sample 2 (Evolutionary PM variant)
"""

from flask import Blueprint, request, jsonify
from models import db, Order, OrderItem, Product, PaymentRequest

order_bp = Blueprint('order_bp', __name__)


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

class OrderItemSerializer:
    """Lightweight serializer for OrderItem rows."""

    FIELDS = ('id', 'product_id', 'quantity', 'unit_price')

    @classmethod
    def one(cls, item: OrderItem) -> dict:
        return {field: getattr(item, field) for field in cls.FIELDS}

    @classmethod
    def many(cls, items) -> list:
        return [cls.one(i) for i in items]


class OrderSerializer:
    """Lightweight serializer for Order rows.

    Supports an `include_items` flag to optionally embed the item list,
    avoiding a separate query when the caller already has items loaded.
    """

    FIELDS = ('id', 'user_id', 'status', 'total_amount', 'created_at')

    @classmethod
    def one(cls, order: Order, include_items: bool = False) -> dict:
        data = {}
        for field in cls.FIELDS:
            value = getattr(order, field)
            if field == 'created_at' and value is not None:
                value = value.isoformat()
            data[field] = value
        if include_items:
            data['items'] = OrderItemSerializer.many(order.items)
        return data

    @classmethod
    def many(cls, orders, include_items: bool = False) -> list:
        return [cls.one(o, include_items=include_items) for o in orders]


# ---------------------------------------------------------------------------
# State machine configuration
# ---------------------------------------------------------------------------

# Maps {current_status: {action_name: new_status}}.
# Actions not listed for a given state are illegal transitions (409).
STATE_TRANSITIONS = {
    'pending':  {'pay': 'paid', 'cancel': 'cancelled'},
    'paid':     {'ship': 'shipped', 'cancel': 'cancelled'},
    'shipped':  {'deliver': 'delivered'},
    'delivered': {},
    'cancelled': {},
}


def _transition_state(order: Order, action: str):
    """Attempt a state transition.

    Returns (new_status, None) on success, or (None, error_message) on failure.
    The caller is responsible for committing or rolling back.
    """
    allowed = STATE_TRANSITIONS.get(order.status, {})
    new_status = allowed.get(action)
    if new_status is None:
        return None, f"Cannot {action} order in '{order.status}' state"
    order.status = new_status
    return new_status, None


# ---------------------------------------------------------------------------
# Helper: batch product lookup
# ---------------------------------------------------------------------------

def _fetch_products_by_ids(product_ids):
    """Fetch products for a set of IDs and return a {id: Product} dict.

    Uses a single query instead of N individual lookups.
    Returns None if any product_id is not found (with the missing id as string).
    """
    products = Product.query.filter(Product.id.in_(product_ids)).all()
    lookup = {p.id: p for p in products}
    missing = set(product_ids) - set(lookup.keys())
    if missing:
        return None, missing.pop()
    return lookup, None


# ---------------------------------------------------------------------------
# Route: POST /orders  (create)
# ---------------------------------------------------------------------------

@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order with stock validation.

    Request body: {"user_id": str, "items": [{"product_id": int, "quantity": int}, ...]}
    Returns 201 on success, 400 on validation error.
    """
    body = request.get_json(silent=True)

    # Guard: valid JSON body
    if not isinstance(body, dict):
        return jsonify({'status': 'error', 'message': 'Request body must be valid JSON'}), 400

    # Guard: required fields
    if 'user_id' not in body or not isinstance(body['user_id'], str):
        return jsonify({'status': 'error', 'message': 'Missing or invalid field: user_id'}), 400

    items_data = body.get('items')
    if not isinstance(items_data, list) or len(items_data) == 0:
        return jsonify({'status': 'error', 'message': 'Field "items" must be a non-empty list'}), 400

    # Collect all product IDs and validate item structure
    product_ids = []
    for idx, item in enumerate(items_data):
        if not isinstance(item, dict):
            return jsonify({'status': 'error', 'message': f'Item {idx} must be a dict'}), 400
        if 'product_id' not in item or 'quantity' not in item:
            return jsonify({'status': 'error', 'message': f'Item {idx} must have product_id and quantity'}), 400
        qty = item['quantity']
        if not isinstance(qty, int) or qty <= 0:
            return jsonify({'status': 'error', 'message': f'Item {idx} quantity must be a positive integer'}), 400
        product_ids.append(item['product_id'])

    # Bulk product lookup
    lookup, missing_id = _fetch_products_by_ids(product_ids)
    if lookup is None:
        return jsonify({'status': 'error', 'message': f'Product {missing_id} not found'}), 400

    # Validate stock for all items
    for item in items_data:
        product = lookup[item['product_id']]
        if product.stock < item['quantity']:
            return jsonify({
                'status': 'error',
                'message': f'Insufficient stock for product {product.id} '
                           f'(requested: {item["quantity"]}, available: {product.stock})',
            }), 400

    # Calculate total and build OrderItem instances
    total_amount = 0.0
    order_items = []
    for item in items_data:
        product = lookup[item['product_id']]
        total_amount += product.price * item['quantity']
        order_items.append(OrderItem(
            product_id=item['product_id'],
            quantity=item['quantity'],
            unit_price=product.price,
        ))

    # Create order and persist
    order = Order(
        user_id=body['user_id'],
        status='pending',
        total_amount=total_amount,
        items=order_items,
    )
    db.session.add(order)
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': OrderSerializer.one(order, include_items=False),
    }), 201


# ---------------------------------------------------------------------------
# Route: GET /orders/<id>  (detail with items)
# ---------------------------------------------------------------------------

@order_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id: int):
    """Get a single order with its items."""
    order = Order.query.get(order_id)

    if order is None:
        return jsonify({'status': 'error', 'message': f'Order {order_id} not found'}), 404

    return jsonify({
        'status': 'ok',
        'data': OrderSerializer.one(order, include_items=True),
    }), 200


# ---------------------------------------------------------------------------
# Route: GET /orders  (list + filter)
# ---------------------------------------------------------------------------

@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders, optionally filtered by user_id and/or status."""
    query = Order.query

    # Dynamic filter construction using filter_by
    filters = {}
    user_id = request.args.get('user_id')
    if user_id is not None:
        filters['user_id'] = user_id

    status = request.args.get('status')
    if status is not None:
        filters['status'] = status

    if filters:
        query = query.filter_by(**filters)

    orders = query.all()
    return jsonify({
        'status': 'ok',
        'data': OrderSerializer.many(orders),
    }), 200


# ---------------------------------------------------------------------------
# Route: POST /orders/<id>/pay  (with idempotency)
# ---------------------------------------------------------------------------

@order_bp.route('/orders/<int:order_id>/pay', methods=['POST'])
def pay_order(order_id: int):
    """Pay for an order (pending -> paid).

    Requires Idempotency-Key header.  Duplicate keys return the same result
    without re-processing or re-deducting stock.
    """
    # Guard: Idempotency-Key header
    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify({'status': 'error', 'message': 'Idempotency-Key header is required'}), 400

    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': f'Order {order_id} not found'}), 404

    # Check for duplicate idempotency key
    existing = PaymentRequest.query.filter_by(
        order_id=order_id, idempotency_key=idempotency_key
    ).first()
    if existing is not None:
        # Idempotent: return the same result without re-processing
        return jsonify({
            'status': 'ok',
            'data': OrderSerializer.one(order, include_items=False),
        }), 200

    # Attempt state transition
    new_status, err = _transition_state(order, 'pay')
    if err:
        return jsonify({'status': 'error', 'message': err}), 409

    # Deduct stock for each order item
    for item in order.items:
        product = Product.query.get(item.product_id)
        if product:
            product.stock -= item.quantity

    # Record idempotency key
    payment = PaymentRequest(
        order_id=order_id,
        idempotency_key=idempotency_key,
        status='processed',
    )
    db.session.add(payment)
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': OrderSerializer.one(order, include_items=False),
    }), 200


# ---------------------------------------------------------------------------
# Route: POST /orders/<id>/ship
# ---------------------------------------------------------------------------

@order_bp.route('/orders/<int:order_id>/ship', methods=['POST'])
def ship_order(order_id: int):
    """Ship an order (paid -> shipped)."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': f'Order {order_id} not found'}), 404

    _, err = _transition_state(order, 'ship')
    if err:
        return jsonify({'status': 'error', 'message': err}), 409

    db.session.commit()
    return jsonify({
        'status': 'ok',
        'data': OrderSerializer.one(order, include_items=False),
    }), 200


# ---------------------------------------------------------------------------
# Route: POST /orders/<id>/deliver
# ---------------------------------------------------------------------------

@order_bp.route('/orders/<int:order_id>/deliver', methods=['POST'])
def deliver_order(order_id: int):
    """Deliver an order (shipped -> delivered)."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': f'Order {order_id} not found'}), 404

    _, err = _transition_state(order, 'deliver')
    if err:
        return jsonify({'status': 'error', 'message': err}), 409

    db.session.commit()
    return jsonify({
        'status': 'ok',
        'data': OrderSerializer.one(order, include_items=False),
    }), 200


# ---------------------------------------------------------------------------
# Route: POST /orders/<id>/cancel
# ---------------------------------------------------------------------------

@order_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id: int):
    """Cancel an order (pending/paid -> cancelled).

    If the order was paid, restores product stock.
    """
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': f'Order {order_id} not found'}), 404

    # Remember previous status before transition (for stock restoration)
    was_paid = order.status == 'paid'

    _, err = _transition_state(order, 'cancel')
    if err:
        return jsonify({'status': 'error', 'message': err}), 409

    # Restore stock if order was previously paid
    if was_paid:
        for item in order.items:
            product = Product.query.get(item.product_id)
            if product:
                product.stock += item.quantity

    db.session.commit()
    return jsonify({
        'status': 'ok',
        'data': OrderSerializer.one(order, include_items=False),
    }), 200
