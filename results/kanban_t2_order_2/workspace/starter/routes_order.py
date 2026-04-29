"""
T2 Order System -- Order Routes

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

from flask import Blueprint, request, jsonify
from models import Product, Order, OrderItem, PaymentRequest, db
from datetime import datetime

order_bp = Blueprint('order_bp', __name__)


def _serialize_order(order):
    """Serialize an order to a JSON-safe dict (without items)."""
    return {
        'id': order.id,
        'user_id': order.user_id,
        'status': order.status,
        'total_amount': order.total_amount,
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'paid_at': order.paid_at.isoformat() if order.paid_at else None,
        'shipped_at': order.shipped_at.isoformat() if order.shipped_at else None,
        'delivered_at': order.delivered_at.isoformat() if order.delivered_at else None,
        'cancelled_at': order.cancelled_at.isoformat() if order.cancelled_at else None,
    }


def _serialize_order_with_items(order):
    """Serialize an order with its items list."""
    data = _serialize_order(order)
    data['items'] = [
        {
            'id': item.id,
            'product_id': item.product_id,
            'quantity': item.quantity,
            'unit_price': item.unit_price,
        }
        for item in order.items
    ]
    return data


# ============================================================
# Order CRUD
# ============================================================

@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order with validated items."""
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'status': 'error', 'message': 'Request body must be JSON'}), 400

    user_id = body.get('user_id')
    items = body.get('items')

    if not user_id or not items or not isinstance(items, list) or len(items) == 0:
        return jsonify({'status': 'error', 'message': 'user_id and non-empty items are required'}), 400

    # Validate all products exist and check stock
    products = {}
    for item in items:
        pid = item.get('product_id')
        qty = item.get('quantity')
        if pid is None or qty is None or qty <= 0:
            return jsonify({'status': 'error', 'message': 'Each item must have product_id and positive quantity'}), 400

        product = Product.query.get(pid)
        if not product:
            return jsonify({'status': 'error', 'message': f'Product {pid} not found'}), 400
        if product.stock < qty:
            return jsonify({'status': 'error', 'message': f'Insufficient stock for product {pid}'}), 400

        products[pid] = (product, qty)

    # Calculate total and create order
    total_amount = 0.0
    order_items = []
    for pid, (product, qty) in products.items():
        total_amount += product.price * qty
        order_items.append(OrderItem(
            product_id=pid,
            quantity=qty,
            unit_price=product.price,
        ))

    order = Order(
        user_id=user_id,
        status='pending',
        total_amount=total_amount,
    )
    order.items = order_items

    db.session.add(order)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_order(order)}), 201


@order_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    """Get order details including items list."""
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    return jsonify({'status': 'ok', 'data': _serialize_order_with_items(order)}), 200


@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders, optionally filtered by user_id and/or status."""
    query = Order.query
    user_id = request.args.get('user_id')
    status = request.args.get('status')

    if user_id:
        query = query.filter(Order.user_id == user_id)
    if status:
        query = query.filter(Order.status == status)

    orders = query.all()
    return jsonify({'status': 'ok', 'data': [_serialize_order(o) for o in orders]}), 200


# ============================================================
# Order state machine (ATU-003)
# ============================================================


@order_bp.route('/orders/<int:order_id>/pay', methods=['POST'])
def pay_order(order_id):
    """Pay for an order: pending -> paid. Requires Idempotency-Key header."""
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify({'status': 'error', 'message': 'Idempotency-Key header is required'}), 400

    # Check for existing payment request with same key (idempotency)
    existing = PaymentRequest.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        # Return the current order state without re-processing
        cached_order = Order.query.get(existing.order_id)
        return jsonify({'status': 'ok', 'data': _serialize_order_with_items(cached_order)}), 200

    # Validate state transition: only pending -> paid
    if order.status != 'pending':
        return jsonify({'status': 'error', 'message': f'Cannot pay order in {order.status} state'}), 409

    # Deduct stock for each order item
    for item in order.items:
        product = Product.query.get(item.product_id)
        product.stock -= item.quantity

    # Update order status
    order.status = 'paid'
    order.paid_at = datetime.utcnow()

    # Create PaymentRequest record
    payment = PaymentRequest(
        order_id=order.id,
        idempotency_key=idempotency_key,
        status='completed',
    )
    db.session.add(payment)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_order_with_items(order)}), 200


@order_bp.route('/orders/<int:order_id>/ship', methods=['POST'])
def ship_order(order_id):
    """Ship an order: paid -> shipped."""
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status != 'paid':
        return jsonify({'status': 'error', 'message': f'Cannot ship order in {order.status} state'}), 409

    order.status = 'shipped'
    order.shipped_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_order_with_items(order)}), 200


@order_bp.route('/orders/<int:order_id>/deliver', methods=['POST'])
def deliver_order(order_id):
    """Deliver an order: shipped -> delivered."""
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status != 'shipped':
        return jsonify({'status': 'error', 'message': f'Cannot deliver order in {order.status} state'}), 409

    order.status = 'delivered'
    order.delivered_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_order_with_items(order)}), 200


@order_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    """Cancel an order: pending/paid -> cancelled. Restores stock if paid."""
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'status': 'error', 'message': 'Order not found'}), 404

    if order.status not in ('pending', 'paid'):
        return jsonify({'status': 'error', 'message': f'Cannot cancel order in {order.status} state'}), 409

    # If paid, restore stock for each order item
    if order.status == 'paid':
        for item in order.items:
            product = Product.query.get(item.product_id)
            product.stock += item.quantity

    order.status = 'cancelled'
    order.cancelled_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_order_with_items(order)}), 200
