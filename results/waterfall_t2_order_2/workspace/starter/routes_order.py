"""
T2 Order System — Order Routes

Implement order CRUD, state machine, and payment with idempotency.
Register as a Flask Blueprint named 'order_bp'.

Order state machine:
  pending → paid → shipped → delivered
  pending/paid → cancelled

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

- POST /orders/<id>/pay -> Pay for order (pending → paid)
  Header: Idempotency-Key (required)
  - Deducts stock from products
  - Records PaymentRequest for idempotency
  - Duplicate Idempotency-Key returns same result without re-processing
  Errors: 404 if order not found, 400 if no key, 409 if invalid state transition

- POST /orders/<id>/ship -> Ship order (paid → shipped)
  Errors: 404 if not found, 409 if invalid state

- POST /orders/<id>/deliver -> Deliver order (shipped → delivered)
  Errors: 404 if not found, 409 if invalid state

- POST /orders/<id>/cancel -> Cancel order (pending/paid → cancelled)
  - Restores product stock if order was paid
  Errors: 404 if not found, 409 if invalid state

IMPORTANT: This module works with models.py (Order, OrderItem, PaymentRequest, Product)
and routes_product.py. Stock deduction happens at payment time, not order creation.
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
from app import db
from models import Product, Order, OrderItem, PaymentRequest

order_bp = Blueprint('order_bp', __name__)


# ============================================================
# Serialization helpers (design.md §5.2, §5.3)
# ============================================================

def order_to_dict(order):
    """Serialize an Order without items."""
    return {
        'id': order.id,
        'user_id': order.user_id,
        'status': order.status,
        'total_amount': order.total_amount,
        'created_at': order.created_at.isoformat() if order.created_at else None,
    }


def order_to_dict_with_items(order):
    """Serialize an Order including its OrderItem list."""
    data = order_to_dict(order)
    data['items'] = [{
        'id': item.id,
        'product_id': item.product_id,
        'quantity': item.quantity,
        'unit_price': item.unit_price,
    } for item in order.items]
    return data


# ============================================================
# Response helpers (design.md §6.1)
# ============================================================

def ok_response(data, status_code=200):
    """Return a unified success response."""
    return jsonify({"status": "ok", "data": data}), status_code


def error_response(status_code, message):
    """Return a unified error response."""
    return jsonify({"status": "error", "message": message}), status_code


# ============================================================
# POST /orders — Create order (design.md §2.2)
# ============================================================

@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create a new order with items.

    Validates all products exist and have sufficient stock.
    Creates Order (status='pending') and OrderItem records.
    """
    body = request.get_json(silent=True)
    if body is None:
        return error_response(400, "Request body must be valid JSON")

    user_id = body.get('user_id')
    items = body.get('items')

    # Validate required fields
    if not user_id:
        return error_response(400, "Field 'user_id' is required")
    if not isinstance(items, list) or len(items) == 0:
        return error_response(400, "Field 'items' must be a non-empty list")

    # Validate each item and resolve products
    products = []
    for idx, item in enumerate(items):
        product_id = item.get('product_id')
        quantity = item.get('quantity')

        if product_id is None:
            return error_response(400, f"Item {idx}: 'product_id' is required")
        if quantity is None or not isinstance(quantity, int) or quantity <= 0:
            return error_response(400, f"Item {idx}: 'quantity' must be a positive integer")

        product = Product.query.get(product_id)
        if product is None:
            return error_response(400, f"Product id {product_id} not found")
        if product.stock < quantity:
            return error_response(400, f"Product '{product.name}' (id={product_id}) insufficient stock: need {quantity}, have {product.stock}")

        products.append((product, quantity))

    # Calculate total amount
    total_amount = sum(product.price * quantity for product, quantity in products)

    # Create Order
    order = Order(user_id=user_id, status='pending', total_amount=total_amount)
    db.session.add(order)
    db.session.flush()  # get order.id before creating OrderItems

    # Create OrderItem records (unit_price = product.price at order time)
    for product, quantity in products:
        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=product.price,
        )
        db.session.add(order_item)

    db.session.commit()

    return ok_response(order_to_dict(order), status_code=201)


# ============================================================
# GET /orders/<int:id> — Get order detail with items (design.md §2.2)
# ============================================================

@order_bp.route('/orders/<int:id>', methods=['GET'])
def get_order(id):
    """Get a single order by ID, including its items."""
    order = Order.query.get_or_404(id)
    return ok_response(order_to_dict_with_items(order))


# ============================================================
# GET /orders — List/filter orders (design.md §2.2)
# ============================================================

@order_bp.route('/orders', methods=['GET'])
def list_orders():
    """List orders with optional filters: user_id, status."""
    query = Order.query

    user_id = request.args.get('user_id')
    if user_id is not None:
        query = query.filter_by(user_id=user_id)

    status = request.args.get('status')
    if status is not None:
        query = query.filter_by(status=status)

    orders = query.all()
    return ok_response([order_to_dict(o) for o in orders])


# ============================================================
# ATU-005: State Machine & Payment (design.md §2.2, §3)
# ============================================================

@order_bp.route('/orders/<int:id>/pay', methods=['POST'])
def pay_order(id):
    """Pay for order (pending -> paid) with idempotency.

    CRITICAL: Idempotency check must happen BEFORE status check.
    This ensures that a duplicate key on an already-paid order
    returns 200 (idempotent) rather than 409.
    """
    # Step 1: Check Idempotency-Key header exists
    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return error_response(400, "Idempotency-Key header is required")

    # Step 2: Check idempotency (BEFORE status check)
    existing = PaymentRequest.query.filter_by(
        order_id=id,
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        order = Order.query.get_or_404(id)
        return ok_response(order_to_dict(order))

    # Step 3: Check order exists
    order = Order.query.get_or_404(id)

    # Step 4: Check order status is pending
    if order.status != 'pending':
        return error_response(409, f"Order is in '{order.status}' state, cannot pay")

    # Step 5: Create PaymentRequest record
    payment = PaymentRequest(
        order_id=id,
        idempotency_key=idempotency_key,
        status='completed',
    )
    db.session.add(payment)

    # Step 6: Deduct stock for each item
    for item in order.items:
        product = Product.query.get(item.product_id)
        product.stock -= item.quantity

    # Step 7: Update order status and timestamps
    order.status = 'paid'
    order.paid_at = datetime.utcnow()

    # Step 8: Commit
    db.session.commit()

    return ok_response(order_to_dict(order))


@order_bp.route('/orders/<int:id>/ship', methods=['POST'])
def ship_order(id):
    """Ship order (paid -> shipped)."""
    order = Order.query.get_or_404(id)

    if order.status != 'paid':
        return error_response(409, f"Order is in '{order.status}' state, cannot ship")

    order.status = 'shipped'
    order.shipped_at = datetime.utcnow()
    db.session.commit()

    return ok_response(order_to_dict(order))


@order_bp.route('/orders/<int:id>/deliver', methods=['POST'])
def deliver_order(id):
    """Deliver order (shipped -> delivered)."""
    order = Order.query.get_or_404(id)

    if order.status != 'shipped':
        return error_response(409, f"Order is in '{order.status}' state, cannot deliver")

    order.status = 'delivered'
    order.delivered_at = datetime.utcnow()
    db.session.commit()

    return ok_response(order_to_dict(order))


@order_bp.route('/orders/<int:id>/cancel', methods=['POST'])
def cancel_order(id):
    """Cancel order (pending/paid -> cancelled).

    If order is in 'paid' state, restores product stock.
    """
    order = Order.query.get_or_404(id)

    if order.status not in ('pending', 'paid'):
        return error_response(409, f"Order is in '{order.status}' state, cannot cancel")

    # If paid, restore stock
    if order.status == 'paid':
        for item in order.items:
            product = Product.query.get(item.product_id)
            product.stock += item.quantity

    order.status = 'cancelled'
    order.cancelled_at = datetime.utcnow()
    db.session.commit()

    return ok_response(order_to_dict(order))
