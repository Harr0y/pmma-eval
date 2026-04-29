"""
T2 Order System -- Order Routes (Gen 1, Sample 1)

Design decisions (declarative state machine variant):

1. **Declarative state machine** -- All valid transitions are defined in a single
   module-level dictionary (STATE_TRANSITIONS). Every transition route delegates to
   a unified _advance_state() function, so adding a new state or edge requires
   editing only the table, not scattered if/elif chains.

2. **Side-effect registry** -- Each transition edge can declare pre/post hooks
   (e.g. stock deduction on pay, stock restore on cancel-paid). These are stored
   alongside the target state in the transition table, keeping side-effect logic
   co-located with the transition definition.

3. **Three-phase handler pattern** (inherited from ATU legacy) --
   validate -> execute -> serialize, keeping route handlers flat.

4. **Standalone serialize()/serialize_list()** (inherited from ATU legacy) --
   decouple ORM-to-dict conversion from handlers.

5. **Structured validation** -- _validate_create_order() returns a tuple of
   (cleaned_data_or_None, error_tuple_or_None) for precise error reporting.
"""

from datetime import datetime
from flask import Blueprint, request, jsonify
from app import db
from models import Product, Order, OrderItem, PaymentRequest

order_bp = Blueprint('order_bp', __name__)


# ---------------------------------------------------------------------------
# Declarative state machine
# ---------------------------------------------------------------------------

# Map: (current_status, action) -> (target_status, side_effects_hook_or_None)
# side_effects_hook signature: hook(order, db_session) -> None
# A None hook means no side effects beyond updating status and timestamps.

def _deduct_stock(order, session):
    """Deduct stock for each order item at payment time."""
    for item in order.items:
        product = Product.query.get(item.product_id)
        product.stock -= item.quantity
    order.paid_at = datetime.utcnow()


def _restore_stock(order, session):
    """Restore stock when cancelling a paid order."""
    for item in order.items:
        product = Product.query.get(item.product_id)
        product.stock += item.quantity


def _record_ship(order, session):
    """Set shipped_at timestamp."""
    order.shipped_at = datetime.utcnow()


def _record_deliver(order, session):
    """Set delivered_at timestamp."""
    order.delivered_at = datetime.utcnow()


def _record_cancel(order, session):
    """Set cancelled_at timestamp."""
    order.cancelled_at = datetime.utcnow()


STATE_TRANSITIONS = {
    ('pending', 'pay'):     ('paid',      _deduct_stock),
    ('paid',    'ship'):    ('shipped',   _record_ship),
    ('shipped', 'deliver'): ('delivered', _record_deliver),
    ('pending', 'cancel'):  ('cancelled', _record_cancel),
    ('paid',    'cancel'):  ('cancelled', _restore_stock),  # stock restore is side effect
}


def _advance_state(order, action):
    """Attempt a state transition on *order* for the given *action*.

    Returns (target_status, hook) on success, or None if the transition
    is invalid for the order's current status.
    """
    key = (order.status, action)
    return STATE_TRANSITIONS.get(key)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _serialize_order_item(item):
    """Convert an OrderItem ORM instance into a plain dict."""
    return {
        'id': item.id,
        'product_id': item.product_id,
        'quantity': item.quantity,
        'unit_price': item.unit_price,
    }


def serialize(order):
    """Convert an Order ORM instance into a plain dict, including items."""
    return {
        'id': order.id,
        'user_id': order.user_id,
        'status': order.status,
        'total_amount': order.total_amount,
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'items': [_serialize_order_item(i) for i in order.items],
    }


def serialize_list(orders):
    """Convert an iterable of Order instances into a list of dicts."""
    return [serialize(o) for o in orders]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_REQUIRED_CREATE_FIELDS = {'user_id', 'items'}


def _validate_create_order(payload):
    """Validate order creation payload.

    Returns (cleaned_data_dict, error_tuple_or_None).
    error_tuple is (field_or_general, description).
    """
    if not isinstance(payload, dict):
        return None, ('body', 'request body must be a JSON object')

    missing = _REQUIRED_CREATE_FIELDS - set(payload.keys())
    if missing:
        return None, (', '.join(sorted(missing)), 'missing required field(s)')

    user_id = payload['user_id']
    if not isinstance(user_id, str) or not user_id:
        return None, ('user_id', 'must be a non-empty string')

    items = payload['items']
    if not isinstance(items, list) or len(items) == 0:
        return None, ('items', 'must be a non-empty list')

    # Validate each item entry
    cleaned_items = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            return None, (f'items[{idx}]', 'must be an object')
        for key in ('product_id', 'quantity'):
            if key not in item:
                return None, (f'items[{idx}].{key}', 'missing required field')
        if not isinstance(item['product_id'], int) or item['product_id'] < 1:
            return None, (f'items[{idx}].product_id', 'must be a positive integer')
        if not isinstance(item['quantity'], int) or item['quantity'] < 1:
            return None, (f'items[{idx}].quantity', 'must be a positive integer')
        cleaned_items.append({
            'product_id': item['product_id'],
            'quantity': item['quantity'],
        })

    return {'user_id': user_id, 'items': cleaned_items}, None


# ---------------------------------------------------------------------------
# Route handlers -- three-phase: validate -> execute -> serialize
# ---------------------------------------------------------------------------

@order_bp.route('/orders', methods=['POST'])
def create_order():
    """POST /orders -- create a new pending order."""
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({'status': 'error', 'message': 'request body must be JSON'}), 400

    # Phase 1: validate
    cleaned, err = _validate_create_order(payload)
    if err is not None:
        field, description = err
        return jsonify({'status': 'error', 'message': f'Invalid field "{field}": {description}'}), 400

    # Phase 2: execute -- check products & stock, then create
    order_items_data = []
    total_amount = 0.0
    for item in cleaned['items']:
        product = Product.query.get(item['product_id'])
        if product is None:
            return jsonify({
                'status': 'error',
                'message': f'Product {item["product_id"]} not found',
            }), 400
        if product.stock < item['quantity']:
            return jsonify({
                'status': 'error',
                'message': f'Insufficient stock for product {product.id} '
                           f'(available: {product.stock}, requested: {item["quantity"]})',
            }), 400
        order_items_data.append((product, item['quantity']))
        total_amount += product.price * item['quantity']

    order = Order(user_id=cleaned['user_id'], status='pending', total_amount=total_amount)
    db.session.add(order)
    db.session.flush()  # get order.id before creating items

    for product, quantity in order_items_data:
        oi = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=product.price,
        )
        db.session.add(oi)

    db.session.commit()

    # Phase 3: serialize
    return jsonify({'status': 'ok', 'data': serialize(order)}), 201


@order_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    """GET /orders/<id> -- return a single order with items."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': f'Order {order_id} not found'}), 404

    return jsonify({'status': 'ok', 'data': serialize(order)}), 200


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """GET /orders -- list/filter orders by user_id and/or status."""
    query = Order.query
    user_id = request.args.get('user_id')
    status = request.args.get('status')
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    if status is not None:
        query = query.filter_by(status=status)
    orders = query.all()
    return jsonify({'status': 'ok', 'data': serialize_list(orders)}), 200


@order_bp.route('/orders/<int:order_id>/pay', methods=['POST'])
def pay_order(order_id):
    """POST /orders/<id>/pay -- pay for order (pending -> paid).

    Requires Idempotency-Key header. Duplicate keys are idempotent.
    """
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': f'Order {order_id} not found'}), 404

    # Validate Idempotency-Key
    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify({'status': 'error', 'message': 'Idempotency-Key header is required'}), 400

    # Check for existing payment request (idempotency)
    existing = PaymentRequest.query.filter_by(idempotency_key=idempotency_key).first()
    if existing is not None:
        # Return the current order state without re-processing
        return jsonify({'status': 'ok', 'data': serialize(order)}), 200

    # Validate state transition via declarative state machine
    transition = _advance_state(order, 'pay')
    if transition is None:
        return jsonify({
            'status': 'error',
            'message': f'Cannot transition order {order_id} from "{order.status}" via "pay"',
        }), 409

    # Execute transition
    target_status, hook = transition
    order.status = target_status
    if hook:
        hook(order, db.session)

    # Record payment request for idempotency
    pr = PaymentRequest(
        order_id=order.id,
        idempotency_key=idempotency_key,
        status='completed',
    )
    db.session.add(pr)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': serialize(order)}), 200


@order_bp.route('/orders/<int:order_id>/ship', methods=['POST'])
def ship_order(order_id):
    """POST /orders/<id>/ship -- ship order (paid -> shipped)."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': f'Order {order_id} not found'}), 404

    transition = _advance_state(order, 'ship')
    if transition is None:
        return jsonify({
            'status': 'error',
            'message': f'Cannot transition order {order_id} from "{order.status}" via "ship"',
        }), 409

    target_status, hook = transition
    order.status = target_status
    if hook:
        hook(order, db.session)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': serialize(order)}), 200


@order_bp.route('/orders/<int:order_id>/deliver', methods=['POST'])
def deliver_order(order_id):
    """POST /orders/<id>/deliver -- deliver order (shipped -> delivered)."""
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': f'Order {order_id} not found'}), 404

    transition = _advance_state(order, 'deliver')
    if transition is None:
        return jsonify({
            'status': 'error',
            'message': f'Cannot transition order {order_id} from "{order.status}" via "deliver"',
        }), 409

    target_status, hook = transition
    order.status = target_status
    if hook:
        hook(order, db.session)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': serialize(order)}), 200


@order_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    """POST /orders/<id>/cancel -- cancel order (pending/paid -> cancelled).

    If the order is paid, product stock is restored.
    """
    order = Order.query.get(order_id)
    if order is None:
        return jsonify({'status': 'error', 'message': f'Order {order_id} not found'}), 404

    transition = _advance_state(order, 'cancel')
    if transition is None:
        return jsonify({
            'status': 'error',
            'message': f'Cannot transition order {order_id} from "{order.status}" via "cancel"',
        }), 409

    target_status, hook = transition
    order.status = target_status
    if hook:
        hook(order, db.session)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': serialize(order)}), 200
