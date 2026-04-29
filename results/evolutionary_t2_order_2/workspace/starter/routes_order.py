"""
T2 Order System -- Order Routes (Sample 2)

Evolutionary variant different from Sample 1:
- OrderStateMachine class encapsulates state transitions and side effects
  instead of a plain dict mapping
- Standalone inventory helper functions (deduct_stock / restore_stock)
  instead of inline loops inside route handlers
- Uses db.session.get() (modern API) instead of legacy Model.query.get()
- A _create_order_txn() helper isolates the creation transaction
"""

from datetime import datetime
from flask import Blueprint, request, jsonify
from app import db
from models import Product, Order, OrderItem, PaymentRequest

order_bp = Blueprint('order_bp', __name__)


# -- Response helpers (inherited pattern) ---------------------------------

def ok_response(data, status_code=200):
    return jsonify({'status': 'ok', 'data': data}), status_code


def error_response(message, status_code):
    return jsonify({'status': 'error', 'message': message}), status_code


# -- Serialization ---------------------------------------------------------

def serialize_order(order):
    return {
        'id': order.id,
        'user_id': order.user_id,
        'status': order.status,
        'total_amount': order.total_amount,
        'created_at': order.created_at.isoformat() if order.created_at else None,
    }


def serialize_order_detail(order):
    result = serialize_order(order)
    result['items'] = [
        {
            'id': item.id,
            'product_id': item.product_id,
            'quantity': item.quantity,
            'unit_price': item.unit_price,
        }
        for item in order.items
    ]
    return result


# -- Inventory helpers (standalone functions) ------------------------------

def deduct_stock(order):
    """Reduce product stock for each item in the order."""
    for item in order.items:
        product = db.session.get(Product, item.product_id)
        if product is not None:
            product.stock -= item.quantity


def restore_stock(order):
    """Restore product stock when a paid order is cancelled."""
    for item in order.items:
        product = db.session.get(Product, item.product_id)
        if product is not None:
            product.stock += item.quantity


# -- State Machine (class-based encapsulation) -----------------------------

class OrderStateMachine:
    """Encapsulates valid transitions and their side effects.

    Unlike a simple dict-based lookup, this class groups every
    transition's validation, status update, and timestamp logic
    in one place.  Adding a new state or transition only requires
    editing this class.
    """

    # Maps (current_status, action) -> new_status
    _TRANSITIONS = {
        ('pending', 'pay'):      'paid',
        ('paid',    'ship'):     'shipped',
        ('shipped', 'deliver'):  'delivered',
        ('pending', 'cancel'):   'cancelled',
        ('paid',    'cancel'):   'cancelled',
    }

    # Maps (current_status, action) -> timestamp field on Order
    _TIMESTAMPS = {
        ('pending', 'pay'):      'paid_at',
        ('paid',    'ship'):     'shipped_at',
        ('shipped', 'deliver'):  'delivered_at',
        ('pending', 'cancel'):   'cancelled_at',
        ('paid',    'cancel'):   'cancelled_at',
    }

    @classmethod
    def can_transition(cls, current_status, action):
        return (current_status, action) in cls._TRANSITIONS

    @classmethod
    def execute(cls, order, action):
        """Perform a state transition on *order*.

        Returns the new status string on success.
        Raises ValueError if the transition is invalid.
        """
        current = order.status
        if not cls.can_transition(current, action):
            raise ValueError(
                f'Invalid transition: {current} -> {action}'
            )

        new_status = cls._TRANSITIONS[(current, action)]
        order.status = new_status

        ts_field = cls._TIMESTAMPS.get((current, action))
        if ts_field is not None:
            setattr(order, ts_field, datetime.utcnow())

        # Side effects tied to specific transitions
        if action == 'pay':
            deduct_stock(order)
        elif action == 'cancel' and current == 'paid':
            restore_stock(order)

        return new_status


# -- Order creation helper -------------------------------------------------

def _create_order_txn(user_id, items_payload):
    """Validate input, check stock, create Order + OrderItems.

    Returns the new Order object.  Raises ValueError on validation failure.
    Caller is responsible for db.session.commit() / rollback.
    """
    product_cache = {}
    total_amount = 0.0

    for entry in items_payload:
        pid = int(entry['product_id'])
        qty = int(entry['quantity'])

        if pid not in product_cache:
            product = db.session.get(Product, pid)
            if product is None:
                raise ValueError(f'Product {pid} not found')
            product_cache[pid] = product

        product = product_cache[pid]
        if product.stock < qty:
            raise ValueError(
                f'Insufficient stock for product {pid}: '
                f'requested {qty}, available {product.stock}'
            )

        total_amount += product.price * qty

    order = Order(user_id=user_id, status='pending', total_amount=total_amount)
    db.session.add(order)
    db.session.flush()  # get order.id before creating items

    for entry in items_payload:
        pid = int(entry['product_id'])
        qty = int(entry['quantity'])
        item = OrderItem(
            order_id=order.id,
            product_id=pid,
            quantity=qty,
            unit_price=product_cache[pid].price,
        )
        db.session.add(item)

    return order


# -- Routes ----------------------------------------------------------------

@order_bp.route('/orders', methods=['POST'])
def create_order():
    payload = request.get_json(silent=True)
    if payload is None:
        return error_response('Request body must be valid JSON', 400)

    required = ('user_id', 'items')
    for field in required:
        if field not in payload:
            return error_response(f'Missing required field: {field}', 400)

    items = payload['items']
    if not isinstance(items, list) or len(items) == 0:
        return error_response('items must be a non-empty list', 400)

    try:
        order = _create_order_txn(payload['user_id'], items)
    except ValueError as exc:
        return error_response(str(exc), 400)

    db.session.commit()
    return ok_response(serialize_order(order), status_code=201)


@order_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    order = db.session.get(Order, order_id)
    if order is None:
        return error_response(f'Order {order_id} not found', 404)
    return ok_response(serialize_order_detail(order))


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    query = Order.query
    user_id = request.args.get('user_id')
    status = request.args.get('status')
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    if status is not None:
        query = query.filter_by(status=status)
    orders = query.all()
    return ok_response([serialize_order(o) for o in orders])


@order_bp.route('/orders/<int:order_id>/pay', methods=['POST'])
def pay_order(order_id):
    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return error_response('Idempotency-Key header is required', 400)

    order = db.session.get(Order, order_id)
    if order is None:
        return error_response(f'Order {order_id} not found', 404)

    # Idempotency: check if this key was already used for this order
    existing = PaymentRequest.query.filter_by(
        idempotency_key=idempotency_key, order_id=order_id
    ).first()
    if existing is not None:
        return ok_response(serialize_order_detail(order))

    try:
        OrderStateMachine.execute(order, 'pay')
    except ValueError as exc:
        return error_response(str(exc), 409)

    payment = PaymentRequest(
        order_id=order_id,
        idempotency_key=idempotency_key,
        status='completed',
    )
    db.session.add(payment)
    db.session.commit()
    return ok_response(serialize_order_detail(order))


@order_bp.route('/orders/<int:order_id>/ship', methods=['POST'])
def ship_order(order_id):
    order = db.session.get(Order, order_id)
    if order is None:
        return error_response(f'Order {order_id} not found', 404)

    try:
        OrderStateMachine.execute(order, 'ship')
    except ValueError as exc:
        return error_response(str(exc), 409)

    db.session.commit()
    return ok_response(serialize_order_detail(order))


@order_bp.route('/orders/<int:order_id>/deliver', methods=['POST'])
def deliver_order(order_id):
    order = db.session.get(Order, order_id)
    if order is None:
        return error_response(f'Order {order_id} not found', 404)

    try:
        OrderStateMachine.execute(order, 'deliver')
    except ValueError as exc:
        return error_response(str(exc), 409)

    db.session.commit()
    return ok_response(serialize_order_detail(order))


@order_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    order = db.session.get(Order, order_id)
    if order is None:
        return error_response(f'Order {order_id} not found', 404)

    try:
        OrderStateMachine.execute(order, 'cancel')
    except ValueError as exc:
        return error_response(str(exc), 409)

    db.session.commit()
    return ok_response(serialize_order_detail(order))
