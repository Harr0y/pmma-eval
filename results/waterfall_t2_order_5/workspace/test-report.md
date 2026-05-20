# T2-2 订单系统 — 测试报告

## 1. 测试概述

- **测试日期**: 2026-05-01
- **测试环境**: Python + Flask + SQLite (:memory:) + pytest
- **测试命令**: `python -m pytest tests/ -v`
- **测试文件**: `tests/test_basic.py`
- **总测试数**: 19
- **通过数**: 19
- **失败数**: 0
- **通过率**: 100%

## 2. 测试结果明细

### 2.1 TestProductCRUD — 商品接口 (3/3 通过)

| # | 测试用例 | 结果 | 验证内容 |
|---|---------|------|---------|
| 1 | test_create_product | ✅ PASS | POST /products 创建商品返回 201 |
| 2 | test_list_products | ✅ PASS | GET /products 返回商品列表 |
| 3 | test_get_product | ✅ PASS | GET /products/<id> 返回商品详情 |

### 2.2 TestOrderCRUD — 订单 CRUD (4/4 通过)

| # | 测试用例 | 结果 | 验证内容 |
|---|---------|------|---------|
| 4 | test_create_order | ✅ PASS | POST /orders 创建订单成功，状态 pending |
| 5 | test_create_order_insufficient_stock | ✅ PASS | POST /orders 库存不足返回 400 |
| 6 | test_create_order_total_calculation | ✅ PASS | 多商品订单 total_amount = 100×2 + 200×3 = 800.0 |
| 7 | test_filter_orders | ✅ PASS | GET /orders?user_id=u1 返回 2 条，?status=pending 返回 3 条 |

### 2.3 TestStateMachine — 状态机 (6/6 通过)

| # | 测试用例 | 结果 | 验证内容 |
|---|---------|------|---------|
| 8 | test_pay_order | ✅ PASS | pending → paid 成功 |
| 9 | test_ship_order | ✅ PASS | paid → shipped 成功 |
| 10 | test_deliver_order | ✅ PASS | shipped → delivered 成功 |
| 11 | test_illegal_pending_to_shipped | ✅ PASS | pending → shipped 返回 409 |
| 12 | test_illegal_paid_to_delivered | ✅ PASS | paid → delivered 返回 409 |
| 13 | test_delivered_cannot_be_cancelled | ✅ PASS | delivered → cancel 返回 409 |

### 2.4 TestInventory — 库存管理 (3/3 通过)

| # | 测试用例 | 结果 | 验证内容 |
|---|---------|------|---------|
| 14 | test_pay_deducts_stock | ✅ PASS | 付款后 stock 从 10 变为 7（扣减 3） |
| 15 | test_cancel_paid_restores_stock | ✅ PASS | 取消已付款订单后 stock 恢复为 10 |
| 16 | test_cancel_pending_no_stock_change | ✅ PASS | 取消 pending 订单后 stock 不变（10） |

### 2.5 TestIdempotency — 支付幂等性 (3/3 通过)

| # | 测试用例 | 结果 | 验证内容 |
|---|---------|------|---------|
| 17 | test_duplicate_pay_same_key | ✅ PASS | 同一 key 重复付款，stock 只扣一次（7） |
| 18 | test_different_key_different_request | ✅ PASS | 不同 key 对已付款订单返回 409 |
| 19 | test_missing_idempotency_key | ✅ PASS | 缺少 Idempotency-Key 返回 400 |

## 3. 验收标准对照

### 3.1 README.md 验收标准（项目交付门控）

| 验收标准 | 结果 | 说明 |
|---------|------|------|
| 1. 所有上述 API 接口可正常调用 | ✅ 通过 | 10 个端点全部实现，19 个测试覆盖核心场景 |
| 2. tests/test_basic.py 中所有测试用例通过 | ✅ 通过 | 19/19 全部通过 |

### 3.2 requirements.md 验收标准逐条对照

#### AC-01: 商品接口

| # | 验收标准 | 测试覆盖 | 结果 |
|---|---------|---------|------|
| 1 | POST /products 创建商品返回 201 | test_create_product | ✅ 直接测试 |
| 2 | GET /products 返回商品列表 | test_list_products | ✅ 直接测试 |
| 3 | GET /products/\<id\> 返回商品详情 | test_get_product | ✅ 直接测试 |
| 4 | GET /products/\<id\> 商品不存在返回 404 | 无独立测试用例 | ⚠️ 代码审查确认实现（routes_product.py L57-58） |

#### AC-02: 订单 CRUD

| # | 验收标准 | 测试覆盖 | 结果 |
|---|---------|---------|------|
| 5 | POST /orders 创建订单成功，状态为 pending | test_create_order | ✅ 直接测试 |
| 6 | POST /orders 库存不足返回 400 | test_create_order_insufficient_stock | ✅ 直接测试 |
| 7 | POST /orders 多商品订单 total_amount 计算正确 | test_create_order_total_calculation | ✅ 直接测试 |
| 8 | GET /orders/\<id\> 返回订单详情（含 items 列表） | 无独立测试用例 | ⚠️ 代码审查确认实现（routes_order.py include_items=True） |
| 9 | GET /orders/\<id\> 订单不存在返回 404 | 无独立测试用例 | ⚠️ 代码审查确认实现（routes_order.py L133-134） |
| 10 | GET /orders?user_id=X 按 user_id 筛选 | test_filter_orders | ✅ 直接测试 |
| 11 | GET /orders?status=Y 按 status 筛选 | test_filter_orders | ✅ 直接测试 |
| 12 | GET /orders 无参数返回所有订单 | 无独立测试用例 | ⚠️ 代码审查确认实现（routes_order.py L138-153 无参数时返回全部） |

#### AC-03: 状态机

| # | 验收标准 | 测试覆盖 | 结果 |
|---|---------|---------|------|
| 13 | pending → paid 成功 | test_pay_order | ✅ 直接测试 |
| 14 | paid → shipped 成功 | test_ship_order | ✅ 直接测试 |
| 15 | shipped → delivered 成功 | test_deliver_order | ✅ 直接测试 |
| 16 | pending → shipped 返回 409 | test_illegal_pending_to_shipped | ✅ 直接测试 |
| 17 | paid → delivered 返回 409 | test_illegal_paid_to_delivered | ✅ 直接测试 |
| 18 | delivered → cancel 返回 409 | test_delivered_cannot_be_cancelled | ✅ 直接测试 |

#### AC-04: 库存管理

| # | 验收标准 | 测试覆盖 | 结果 |
|---|---------|---------|------|
| 19 | 付款时扣减商品库存 | test_pay_deducts_stock | ✅ 直接测试 |
| 20 | 取消已付款订单恢复库存 | test_cancel_paid_restores_stock | ✅ 直接测试 |
| 21 | 取消 pending 订单不影响库存 | test_cancel_pending_no_stock_change | ✅ 直接测试 |

#### AC-05: 支付幂等性

| # | 验收标准 | 测试覆盖 | 结果 |
|---|---------|---------|------|
| 22 | 同一 Idempotency-Key 重复请求只扣一次库存 | test_duplicate_pay_same_key | ✅ 直接测试 |
| 23 | 不同 Idempotency-Key 对已付款订单返回 409 | test_different_key_different_request | ✅ 直接测试 |
| 24 | 缺少 Idempotency-Key 返回 400 | test_missing_idempotency_key | ✅ 直接测试 |

### 3.3 覆盖统计

| 维度 | 数量 |
|------|------|
| 验收标准总数 | 24 条 |
| 直接测试覆盖 | 20 条（83%） |
| 代码审查确认 | 4 条（17%） |
| 未覆盖 | 0 条 |

**注**：19 个测试函数覆盖了 20 条验收标准（其中 `test_filter_orders` 一个测试同时覆盖了 #10 和 #11 两条标准）。标记为 ⚠️ 的 4 条验收标准（#4、#8、#9、#12）在 test_basic.py 中没有独立测试用例，但已通过代码审查确认实现正确。test_basic.py 是项目预置的测试文件，不在本次开发修改范围内。

## 4. 已知非功能性告警

测试运行中存在 97 个 warnings，均为 SQLAlchemy 2.0 兼容性警告：
- `LegacyAPIWarning: Query.get()` — 建议迁移为 `Session.get()`
- `DeprecationWarning: datetime.utcnow()` — 建议迁移为 `datetime.now(datetime.UTC)`

这些告警不影响业务逻辑正确性，属于框架版本迁移提示。

## 5. 总体结论

**测试通过，达到交付标准。**

- README.md 验收标准全部满足：所有 API 接口可正常调用，test_basic.py 19/19 全部通过
- requirements.md 24 条验收标准全部满足（20 条直接测试 + 4 条代码审查确认）
- 实现文件：`starter/routes_product.py`（3 个端点）+ `starter/routes_order.py`（7 个端点）
