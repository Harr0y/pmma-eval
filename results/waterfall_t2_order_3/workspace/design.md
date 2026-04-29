# Design Document — T2-2 Order System

## 1. Architecture Overview

```
app.py (DO NOT MODIFY)
  ├── models.py (DONE — Product, Order, OrderItem, PaymentRequest)
  ├── routes_product.py (ATU-003 — Product CRUD)
  └── routes_order.py (ATU-004 — Order CRUD + State Machine + Payment)
```

All modules share the same `db` instance from `app.py` via `from app import db`.

## 2. Module Design

### 2.1 routes_product.py (ATU-003)

**Blueprint**: `product_bp`

#### 2.1.1 POST /products — Create Product

```python
@product_bp.route('/products', methods=['POST'])
def create_product():
    data = request.get_json()
    # Validate required fields: name, price, stock
    if not data or 'name' not in data or 'price' not in data or 'stock' not in data:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400
    product = Product(name=data['name'], price=data['price'], stock=data['stock'])
    db.session.add(product)
    db.session.commit()
    return jsonify({"status": "ok", "data": {"id": product.id, "name": product.name, "price": product.price, "stock": product.stock}}), 201
```

#### 2.1.2 GET /products — List Products

```python
@product_bp.route('/products', methods=['GET'])
def list_products():
    products = Product.query.all()
    data = [{"id": p.id, "name": p.name, "price": p.price, "stock": p.stock} for p in products]
    return jsonify({"status": "ok", "data": data}), 200
```

#### 2.1.3 GET /products/<id> — Get Product

```python
@product_bp.route('/products/<int:id>', methods=['GET'])
def get_product(id):
    product = Product.query.get(id)
    if not product:
        return jsonify({"status": "error", "message": "Product not found"}), 404
    return jsonify({"status": "ok", "data": {"id": product.id, "name": product.name, "price": product.price, "stock": product.stock}}), 200
```

### 2.2 routes_order.py (ATU-004)

**Blueprint**: `order_bp`

**Imports**: `from models import Product, Order, OrderItem, PaymentRequest, db` (via app)

#### 2.2.1 POST /orders — Create Order

**Logic**:
1. Parse JSON body: `user_id` (string), `items` (list of `{product_id, quantity}`)
2. Validate: `user_id` and `items` must be present and non-empty
3. For each item:
   a. Look up `Product.query.get(product_id)` → 400 if not found
   b. Check `product.stock >= quantity` → 400 if insufficient
4. Calculate `total_amount = sum(product.price * quantity for each item)`
5. Create `Order` record (status='pending', total_amount=computed)
6. Create `OrderItem` records (unit_price = product.price at creation time)
7. **Do NOT deduct stock** at creation time
8. Return 201 with order data

**Error handling**:
- Missing `user_id` or `items` → 400
- Product not found → 400
- Insufficient stock → 400

#### 2.2.2 GET /orders/<id> — Get Order Detail

**Logic**:
1. `Order.query.get(id)` → 404 if not found
2. Serialize order + items list
3. Return 200

**Response structure**:
```json
{
  "status": "ok",
  "data": {
    "id": 1, "user_id": "u1", "status": "pending",
    "total_amount": 200.0, "created_at": "...",
    "items": [
      {"id": 1, "product_id": 1, "quantity": 2, "unit_price": 100.0}
    ]
  }
}
```

#### 2.2.3 GET /orders — List/Filter Orders

**Logic**:
1. Build query: `Order.query`
2. If `user_id` param → filter by `Order.user_id == user_id`
3. If `status` param → filter by `Order.status == status`
4. Execute query → return list
5. Return 200

#### 2.2.4 POST /orders/<id>/pay — Pay Order

**Logic**:
1. `Order.query.get(id)` → 404 if not found
2. Check `Idempotency-Key` header → 400 if missing
3. Check `PaymentRequest.query.filter_by(idempotency_key=key).first()`:
   - If exists → return existing order data (idempotent), status 200
4. Check `order.status == 'pending'` → 409 if not
5. Deduct stock: for each item in `order.items`, `product.stock -= item.quantity`
6. Create `PaymentRequest(order_id=order.id, idempotency_key=key, status='completed')`
7. Update `order.status = 'paid'`, `order.paid_at = datetime.utcnow()`
8. Commit
9. Return 200

**Key design decisions**:
- Idempotency check BEFORE state check (so duplicate requests always succeed)
- Stock deduction happens atomically with status change in same commit

#### 2.2.5 POST /orders/<id>/ship — Ship Order

**Logic**:
1. `Order.query.get(id)` → 404
2. Check `order.status == 'paid'` → 409 if not
3. Update `order.status = 'shipped'`, `order.shipped_at = datetime.utcnow()`
4. Commit → 200

#### 2.2.6 POST /orders/<id>/deliver — Deliver Order

**Logic**:
1. `Order.query.get(id)` → 404
2. Check `order.status == 'shipped'` → 409 if not
3. Update `order.status = 'delivered'`, `order.delivered_at = datetime.utcnow()`
4. Commit → 200

#### 2.2.7 POST /orders/<id>/cancel — Cancel Order

**Logic**:
1. `Order.query.get(id)` → 404
2. Check `order.status in ('pending', 'paid')` → 409 if not
3. If `order.status == 'paid'`: restore stock for each item (`product.stock += item.quantity`)
4. Update `order.status = 'cancelled'`, `order.cancelled_at = datetime.utcnow()`
5. Commit → 200

## 3. State Machine Implementation

Use a simple conditional check pattern (no external library needed):

```python
VALID_TRANSITIONS = {
    'pending': {'paid', 'cancelled'},
    'paid': {'shipped', 'cancelled'},
    'shipped': {'delivered'},
    'delivered': set(),
    'cancelled': set(),
}
```

For each state transition endpoint, check:
```python
if new_status not in VALID_TRANSITIONS.get(order.status, set()):
    return jsonify({"status": "error", "message": f"Invalid state transition from {order.status}"}), 409
```

**Special case for pay**: Idempotency check must happen BEFORE state check to ensure duplicate keys are handled correctly.

## 4. Inventory Management Design

| Operation | Stock Change | Condition |
|-----------|-------------|-----------|
| Create order | None | Always |
| Pay order | `-quantity` per item | At payment time |
| Cancel pending order | None | No stock was deducted |
| Cancel paid order | `+quantity` per item | Rollback |

## 5. Idempotency Design

**Mechanism**: `PaymentRequest` table with UNIQUE `idempotency_key`

**Flow**:
```
Request with Idempotency-Key
    ↓
Check PaymentRequest table for existing key
    ↓ (exists)
Return stored result (200, no side effects)
    ↓ (not exists)
Proceed with payment (state check + stock deduction)
    ↓
Create PaymentRequest record
    ↓
Commit all together
```

**Error handling for duplicate key on insert**: Since we check before inserting, the UNIQUE constraint violation should not occur in normal flow. However, wrapping the insert in a try/except for `IntegrityError` provides defense-in-depth.

## 6. Implementation ATU Execution Order

| Order | ATU | Description | Files | Estimated Lines |
|-------|-----|-------------|-------|-----------------|
| 1 | ATU-003 | Product Routes | `routes_product.py` | ~30 lines |
| 2 | ATU-004 | Order Routes | `routes_order.py` | ~120 lines |

**Dependencies**: ATU-003 must complete before ATU-004 (tests for order creation depend on product creation).

## 7. Response Serialization

All datetime fields should be serialized to ISO 8601 string format using `.isoformat()`.

Product serialization helper:
```python
def product_to_dict(p):
    return {"id": p.id, "name": p.name, "price": p.price, "stock": p.stock}
```

Order serialization helper:
```python
def order_to_dict(o):
    return {
        "id": o.id, "user_id": o.user_id, "status": o.status,
        "total_amount": o.total_amount,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        "shipped_at": o.shipped_at.isoformat() if o.shipped_at else None,
        "delivered_at": o.delivered_at.isoformat() if o.delivered_at else None,
        "cancelled_at": o.cancelled_at.isoformat() if o.cancelled_at else None,
        "items": [{"id": i.id, "product_id": i.product_id, "quantity": i.quantity, "unit_price": i.unit_price} for i in o.items]
    }
```

**Note**: Tests do not verify datetime format, but consistent serialization is good practice.
