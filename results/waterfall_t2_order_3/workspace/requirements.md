# Requirements Document — T2-2 Order System

## 1. Overview

Implement a multi-module Flask order management system with:
- Product CRUD operations
- Order lifecycle management (CRUD + state machine)
- Inventory management (stock deduction at payment, rollback on cancel)
- Idempotent payment processing

## 2. Data Model Requirements

### 2.1 Product
| Field | Type | Constraints |
|-------|------|-------------|
| id | Integer | PK, auto-increment |
| name | String(120) | NOT NULL |
| price | Float | NOT NULL |
| stock | Integer | NOT NULL, default 0 |

### 2.2 Order
| Field | Type | Constraints |
|-------|------|-------------|
| id | Integer | PK, auto-increment |
| user_id | String(50) | NOT NULL |
| status | String(20) | NOT NULL, default 'pending' |
| total_amount | Float | NOT NULL, default 0.0 |
| created_at | DateTime | auto-set |
| paid_at | DateTime | nullable |
| shipped_at | DateTime | nullable |
| delivered_at | DateTime | nullable |
| cancelled_at | DateTime | nullable |
| items | relationship | OrderItem list |

### 2.3 OrderItem
| Field | Type | Constraints |
|-------|------|-------------|
| id | Integer | PK, auto-increment |
| order_id | Integer | FK → order.id, NOT NULL |
| product_id | Integer | FK → product.id, NOT NULL |
| quantity | Integer | NOT NULL |
| unit_price | Float | NOT NULL |

### 2.4 PaymentRequest
| Field | Type | Constraints |
|-------|------|-------------|
| id | Integer | PK, auto-increment |
| order_id | Integer | FK → order.id, NOT NULL |
| idempotency_key | String(200) | NOT NULL, UNIQUE |
| status | String(20) | NOT NULL, default 'pending' |
| created_at | DateTime | auto-set |

## 3. Functional Requirements

### 3.1 Product Routes (`routes_product.py`)

#### FR-P1: Create Product
- **Endpoint**: `POST /products`
- **Request Body**: `{"name": str, "price": float, "stock": int}`
- **Success Response** (201): `{"status": "ok", "data": {"id": int, "name": str, "price": float, "stock": int}}`
- **Error Response** (400): `{"status": "error", "message": "..."}` when required fields missing

#### FR-P2: List Products
- **Endpoint**: `GET /products`
- **Success Response** (200): `{"status": "ok", "data": [...]}`

#### FR-P3: Get Product
- **Endpoint**: `GET /products/<id>`
- **Success Response** (200): `{"status": "ok", "data": {"id": int, "name": str, "price": float, "stock": int}}`
- **Error Response** (404): `{"status": "error", "message": "..."}` when product not found

### 3.2 Order Routes (`routes_order.py`)

#### FR-O1: Create Order
- **Endpoint**: `POST /orders`
- **Request Body**: `{"user_id": str, "items": [{"product_id": int, "quantity": int}, ...]}`
- **Success Response** (201): `{"status": "ok", "data": {"id": int, "user_id": str, "status": "pending", "total_amount": float, "created_at": str}}`
- **Validation Rules**:
  - All products must exist → 400 if any product not found
  - Sufficient stock for all items → 400 if insufficient stock
  - `total_amount` = sum of (product.price × quantity) for all items
- **Behavior**: Creates Order + OrderItem records. Does NOT deduct stock at creation time.

#### FR-O2: Get Order Detail
- **Endpoint**: `GET /orders/<id>`
- **Success Response** (200): `{"status": "ok", "data": {"id": int, "user_id": str, "status": str, "total_amount": float, "created_at": str, "items": [{"id": int, "product_id": int, "quantity": int, "unit_price": float}, ...]}}`
- **Error Response** (404): Order not found

#### FR-O3: List/Filter Orders
- **Endpoint**: `GET /orders?user_id=X&status=Y`
- **Query Parameters**: `user_id` (optional), `status` (optional)
- **Success Response** (200): `{"status": "ok", "data": [...]}`
- **Behavior**: Filter by both or either parameter

#### FR-O4: Pay Order
- **Endpoint**: `POST /orders/<id>/pay`
- **Required Header**: `Idempotency-Key`
- **State Transition**: `pending` → `paid`
- **Side Effects**:
  - Deducts stock from all products in the order (Product.stock -= OrderItem.quantity)
  - Sets `paid_at` timestamp
  - Creates PaymentRequest record with the idempotency key
- **Idempotency Behavior**:
  - Missing `Idempotency-Key` header → 400
  - Duplicate `Idempotency-Key` for same order → return existing result without re-processing (no double stock deduction)
  - Different `Idempotency-Key` for already-paid order → 409 (invalid state)
- **Error Responses**: 404 (order not found), 400 (no idempotency key), 409 (invalid state)

#### FR-O5: Ship Order
- **Endpoint**: `POST /orders/<id>/ship`
- **State Transition**: `paid` → `shipped`
- **Side Effects**: Sets `shipped_at` timestamp
- **Error Responses**: 404 (not found), 409 (invalid state)

#### FR-O6: Deliver Order
- **Endpoint**: `POST /orders/<id>/deliver`
- **State Transition**: `shipped` → `delivered`
- **Side Effects**: Sets `delivered_at` timestamp
- **Error Responses**: 404 (not found), 409 (invalid state)

#### FR-O7: Cancel Order
- **Endpoint**: `POST /orders/<id>/cancel`
- **State Transitions**: `pending` → `cancelled`, `paid` → `cancelled`
- **Side Effects**:
  - Sets `cancelled_at` timestamp
  - If order was `paid`, restores stock for all items (Product.stock += OrderItem.quantity)
- **Error Responses**: 404 (not found), 409 (invalid state — e.g., shipped or delivered cannot be cancelled)

## 4. State Machine

```
pending ──pay──→ paid ──ship──→ shipped ──deliver──→ delivered
   │                 │
   └────cancel───────┘
```

### Valid Transitions
| From | To | Trigger |
|------|----|---------|
| pending | paid | Pay (with idempotency) |
| pending | cancelled | Cancel (no stock change) |
| paid | shipped | Ship |
| paid | cancelled | Cancel (restore stock) |
| shipped | delivered | Deliver |

### Invalid Transitions (return 409)
| From | To | Example |
|------|----|---------|
| pending | shipped | Cannot skip payment |
| pending | delivered | Cannot skip payment+shipping |
| paid | delivered | Cannot skip shipping |
| shipped | cancelled | Cannot cancel after shipping |
| shipped | paid | Cannot reverse |
| shipped | pending | Cannot reverse |
| delivered | cancelled | Cannot cancel after delivery |
| delivered | paid | Cannot reverse |
| delivered | shipped | Cannot reverse |
| delivered | pending | Cannot reverse |
| cancelled | * | Terminal state, no transitions allowed |

> **General Rule**: All state transitions not listed in the Valid Transitions table above shall return 409 Conflict.

## 5. Cross-Cutting Requirements

### 5.1 Response Format
All responses use one of two formats:
- **Success**: `{"status": "ok", "data": ...}`
- **Error**: `{"status": "error", "message": "错误描述"}`

### 5.2 Module Constraints
- `app.py` must NOT be modified (Flask app factory + DB initialization)
- `models.py` is already implemented and correct
- `routes_product.py` and `routes_order.py` must use Blueprint pattern
- Cross-module imports: order routes import Product model for stock operations

### 5.2a Concurrency Assumption
This specification does not address concurrent stock deduction. All operations are assumed to execute sequentially in a single-threaded context.

### 5.3 Inventory Rules
- Stock is NOT reserved at order creation time
- Stock is deducted at payment time only
- Stock is restored when a paid order is cancelled
- Cancelling a pending order does NOT affect stock

### 5.4 Idempotency Rules
- `Idempotency-Key` header is REQUIRED for payment
- Same key + same order → idempotent (return previous result, no side effects)
- Same key + different order → will fail due to UNIQUE constraint on `idempotency_key` column in PaymentRequest table (return 400 or 500; tests do not cover this scenario)
- Missing key → 400 error

## 6. Acceptance Criteria

### AC-1: All API Endpoints Functional
- [ ] POST /products → 201 with correct data
- [ ] GET /products → 200 with product list
- [ ] GET /products/<id> → 200 with product detail / 404 if not found
- [ ] POST /orders → 201 with pending order
- [ ] GET /orders/<id> → 200 with order + items / 404 if not found
- [ ] GET /orders?user_id=X&status=Y → 200 with filtered list
- [ ] POST /orders/<id>/pay → 200 with paid status
- [ ] POST /orders/<id>/ship → 200 with shipped status
- [ ] POST /orders/<id>/deliver → 200 with delivered status
- [ ] POST /orders/<id>/cancel → 200 with cancelled status

### AC-2: Test Suite Passes
All 19 test cases in `tests/test_basic.py` must pass:
- `TestProductCRUD` (3 tests): create, list, get
- `TestOrderCRUD` (4 tests): create, insufficient stock, total calculation, filter
- `TestStateMachine` (6 tests): pay, ship, deliver, illegal pending→shipped, illegal paid→delivered, delivered cannot cancel
- `TestInventory` (3 tests): pay deducts stock, cancel paid restores stock, cancel pending no stock change
- `TestIdempotency` (3 tests): duplicate key idempotent, different key 409, missing key 400

### AC-3: Edge Cases
- Invalid state transitions return 409 (not 500)
- Missing Idempotency-Key returns 400
- Non-existent product/order returns 404
- Insufficient stock returns 400
- Duplicate idempotency key does not double-deduct stock
