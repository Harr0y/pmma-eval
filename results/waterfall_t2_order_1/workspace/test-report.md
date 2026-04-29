# T2-2 测试报告

## 1. 测试概述

- **测试文件**：tests/test_basic.py
- **测试框架**：pytest
- **测试日期**：2026-04-26
- **测试环境**：Python + Flask + SQLite（内存数据库）

## 2. 测试结果

**19 passed, 0 failed, 0 errors — 总耗时 0.37s**

## 3. 逐条验收标准对照

| # | 验收标准 | 判定 | 覆盖测试 |
|---|---------|------|---------|
| 1 | 所有 7 个订单 API 接口可正常调用 | **PASS** | test_create_order, test_filter_orders, test_pay_order, test_ship_order, test_deliver_order, test_delivered_cannot_be_cancelled, test_get_order |
| 2 | 所有 3 个商品 API 接口可正常调用 | **PASS** | test_create_product, test_list_products, test_get_product |
| 3 | tests/test_basic.py 中所有测试用例通过 | **PASS** | 19/19 全部通过 |
| 4 | 状态机非法转换返回 409 | **PASS** | test_illegal_pending_to_shipped, test_illegal_paid_to_delivered, test_delivered_cannot_be_cancelled |
| 5 | 幂等支付正确 | **PASS** | test_duplicate_pay_same_key, test_different_key_different_request, test_missing_idempotency_key |
| 6 | 库存扣减和回滚逻辑正确 | **PASS** | test_pay_deducts_stock, test_cancel_paid_restores_stock, test_cancel_pending_no_stock_change |
| 7 | 输入验证返回 400 | **PASS** | test_create_order_insufficient_stock, test_missing_idempotency_key |

## 4. 测试用例明细

| 测试类 | 测试用例 | 状态 |
|--------|---------|------|
| TestProductCRUD | test_create_product | PASSED |
| TestProductCRUD | test_list_products | PASSED |
| TestProductCRUD | test_get_product | PASSED |
| TestOrderCRUD | test_create_order | PASSED |
| TestOrderCRUD | test_create_order_insufficient_stock | PASSED |
| TestOrderCRUD | test_create_order_total_calculation | PASSED |
| TestOrderCRUD | test_filter_orders | PASSED |
| TestStateMachine | test_pay_order | PASSED |
| TestStateMachine | test_ship_order | PASSED |
| TestStateMachine | test_deliver_order | PASSED |
| TestStateMachine | test_illegal_pending_to_shipped | PASSED |
| TestStateMachine | test_illegal_paid_to_delivered | PASSED |
| TestStateMachine | test_delivered_cannot_be_cancelled | PASSED |
| TestInventory | test_pay_deducts_stock | PASSED |
| TestInventory | test_cancel_paid_restores_stock | PASSED |
| TestInventory | test_cancel_pending_no_stock_change | PASSED |
| TestIdempotency | test_duplicate_pay_same_key | PASSED |
| TestIdempotency | test_different_key_different_request | PASSED |
| TestIdempotency | test_missing_idempotency_key | PASSED |

## 5. 已知问题（非阻塞）

| 问题 | 严重度 | 说明 |
|------|--------|------|
| `Product.query.get(id)` LegacyAPIWarning | 低 | routes_product.py 使用已废弃 API，建议改为 `db.session.get()` |
| `datetime.utcnow()` 弃用警告 | 低 | Python 3.12+ 标记弃用，建议改为 `datetime.now(datetime.UTC)` |
| 测试覆盖盲区 | 建议 | shipped→cancelled、商品不存在创建订单、items 空列表等边界场景无显式测试 |

## 6. 总体评估

**符合交付标准。** 所有 7 条验收标准全部通过，19 个测试用例全部 PASSED。
