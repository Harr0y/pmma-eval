# Test Report — T2-2 Order System

## Summary

| Metric | Value |
|--------|-------|
| Total Tests | 19 |
| Passed | 19 |
| Failed | 0 |
| Pass Rate | 100% |
| Test Framework | pytest |
| Execution Time | ~0.39s |

## Test Results by Category

### TestProductCRUD (3/3 PASSED)

| # | Test | Description | Result |
|---|------|-------------|--------|
| 1 | `test_create_product` | POST /products returns 201 with correct data | ✅ PASSED |
| 2 | `test_list_products` | GET /products returns 200 with product list | ✅ PASSED |
| 3 | `test_get_product` | GET /products/<id> returns 200 with price=99.9 | ✅ PASSED |

### TestOrderCRUD (4/4 PASSED)

| # | Test | Description | Result |
|---|------|-------------|--------|
| 4 | `test_create_order` | POST /orders returns 201, status=pending, user_id correct | ✅ PASSED |
| 5 | `test_create_order_insufficient_stock` | POST /orders returns 400 when stock < quantity | ✅ PASSED |
| 6 | `test_create_order_total_calculation` | Multi-item order total = 100×2 + 200×3 = 800.0 | ✅ PASSED |
| 7 | `test_filter_orders` | GET /orders?user_id=X returns 2, ?status=pending returns 3 | ✅ PASSED |

### TestStateMachine (6/6 PASSED)

| # | Test | Description | Result |
|---|------|-------------|--------|
| 8 | `test_pay_order` | pending → paid via POST /orders/<id>/pay | ✅ PASSED |
| 9 | `test_ship_order` | paid → shipped via POST /orders/<id>/ship | ✅ PASSED |
| 10 | `test_deliver_order` | shipped → delivered via POST /orders/<id>/deliver | ✅ PASSED |
| 11 | `test_illegal_pending_to_shipped` | pending → shipped returns 409 | ✅ PASSED |
| 12 | `test_illegal_paid_to_delivered` | paid → delivered returns 409 | ✅ PASSED |
| 13 | `test_delivered_cannot_be_cancelled` | delivered → cancelled returns 409 | ✅ PASSED |

### TestInventory (3/3 PASSED)

| # | Test | Description | Result |
|---|------|-------------|--------|
| 14 | `test_pay_deducts_stock` | Payment deducts stock: 10 → 7 (quantity=3) | ✅ PASSED |
| 15 | `test_cancel_paid_restores_stock` | Cancel paid order restores stock: 7 → 10 | ✅ PASSED |
| 16 | `test_cancel_pending_no_stock_change` | Cancel pending order: stock stays 10 | ✅ PASSED |

### TestIdempotency (3/3 PASSED)

| # | Test | Description | Result |
|---|------|-------------|--------|
| 17 | `test_duplicate_pay_same_key` | Same Idempotency-Key deducts stock only once | ✅ PASSED |
| 18 | `test_different_key_different_request` | Different key for paid order returns 409 | ✅ PASSED |
| 19 | `test_missing_idempotency_key` | Missing Idempotency-Key returns 400 | ✅ PASSED |

## Acceptance Criteria Verification

### AC-1: All API Endpoints Functional
- ✅ POST /products → 201
- ✅ GET /products → 200
- ✅ GET /products/<id> → 200 / 404
- ✅ POST /orders → 201
- ✅ GET /orders/<id> → 200 / 404
- ✅ GET /orders?user_id=X&status=Y → 200
- ✅ POST /orders/<id>/pay → 200
- ✅ POST /orders/<id>/ship → 200
- ✅ POST /orders/<id>/deliver → 200
- ✅ POST /orders/<id>/cancel → 200

### AC-2: Test Suite Passes (19/19)
- ✅ All 19 test cases pass

### AC-3: Edge Cases
- ✅ Invalid state transitions return 409
- ✅ Missing Idempotency-Key returns 400
- ✅ Non-existent product/order returns 404
- ✅ Insufficient stock returns 400
- ✅ Duplicate idempotency key does not double-deduct stock

## Known Warnings (Non-blocking)

1. **SQLAlchemy LegacyAPIWarning**: `Query.get()` deprecated in SQLAlchemy 2.0. Locations: `routes_product.py:57`, `routes_order.py:65,124,145,165,183,201,211`. Recommendation: migrate to `db.session.get(Model, id)`.
2. **DeprecationWarning**: `datetime.utcnow()` deprecated in Python 3.12+. Locations: `routes_order.py:154,173,191,215`. Recommendation: use `datetime.now(datetime.UTC)`.

## Conclusion

**PASS** — All 19 test cases pass. The implementation meets all acceptance criteria defined in requirements.md.
