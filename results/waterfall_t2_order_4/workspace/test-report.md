# 测试报告 — T2-2 订单系统

## 测试概要

| 项目 | 结果 |
|------|------|
| 测试框架 | pytest |
| 测试文件 | tests/test_basic.py |
| 总测试数 | 19 |
| 通过 | 19 |
| 失败 | 0 |
| 错误 | 0 |
| 执行时间 | 0.40s |

## 验收标准逐条验证

| # | 验收标准 | 结果 | 覆盖测试 |
|---|---------|------|---------|
| 1 | 商品 API 接口可正常调用 | ✅ PASS | TestProductCRUD (3 tests) |
| 2 | 订单 API 接口可正常调用 | ✅ PASS | TestOrderCRUD + TestStateMachine (8 tests) |
| 3 | 状态机合法跳转，非法返回 409 | ✅ PASS | TestStateMachine (6 tests) |
| 4 | 库存扣减/回滚正确 | ✅ PASS | TestInventory (3 tests) |
| 5 | 幂等性：重复 key 不重复扣库存 | ✅ PASS | TestIdempotency::test_duplicate_pay_same_key |
| 6 | 不同 key 返回 409 | ✅ PASS | TestIdempotency::test_different_key_different_request |
| 7 | 缺少 key 返回 400 | ✅ PASS | TestIdempotency::test_missing_idempotency_key |
| 8 | 19 个测试全部通过 | ✅ PASS | 19/19 PASSED |

## 测试用例详细结果

### TestProductCRUD（商品 CRUD）

| 测试 | 结果 | 验证点 |
|------|------|--------|
| test_create_product | PASSED | POST /products 返回 201，响应格式正确 |
| test_list_products | PASSED | GET /products 返回商品列表 |
| test_get_product | PASSED | GET /products/\<id\> 返回商品详情，price=99.9 |

### TestOrderCRUD（订单 CRUD）

| 测试 | 结果 | 验证点 |
|------|------|--------|
| test_create_order | PASSED | POST /orders 返回 201，status=pending |
| test_create_order_insufficient_stock | PASSED | 库存不足返回 400 |
| test_create_order_total_calculation | PASSED | 多商品总价 = 2×100 + 3×200 = 800 |
| test_filter_orders | PASSED | 按 user_id/status 筛选正确 |

### TestStateMachine（状态机）

| 测试 | 结果 | 验证点 |
|------|------|--------|
| test_pay_order | PASSED | pending → paid |
| test_ship_order | PASSED | paid → shipped |
| test_deliver_order | PASSED | shipped → delivered |
| test_illegal_pending_to_shipped | PASSED | pending → shipped 返回 409 |
| test_illegal_paid_to_delivered | PASSED | paid → delivered 返回 409 |
| test_delivered_cannot_be_cancelled | PASSED | delivered → cancel 返回 409 |

### TestInventory（库存管理）

| 测试 | 结果 | 验证点 |
|------|------|--------|
| test_pay_deducts_stock | PASSED | 付款扣库存：10 → 7 |
| test_cancel_paid_restores_stock | PASSED | 取消已付款回滚：10 → 7 → 10 |
| test_cancel_pending_no_stock_change | PASSED | 取消 pending 不影响库存：10 → 10 |

### TestIdempotency（幂等性）

| 测试 | 结果 | 验证点 |
|------|------|--------|
| test_duplicate_pay_same_key | PASSED | 重复 key 不重复扣库存 |
| test_different_key_different_request | PASSED | 不同 key 返回 409 |
| test_missing_idempotency_key | PASSED | 缺少 key 返回 400 |

## 已知非功能问题

| 问题 | 严重程度 | 说明 |
|------|---------|------|
| SQLAlchemy LegacyAPIWarning | 低 | `Query.get()` 在 SQLAlchemy 2.0 中已废弃，建议迁移至 `Session.get()` |
| datetime.utcnow() 弃用 | 低 | Python 3.12+ 中已弃用，建议使用 `datetime.now(datetime.UTC)` |

## 结论

**全部 8 项验收标准通过，19 个测试用例全部通过。项目符合交付标准。**
