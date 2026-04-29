# T2-2 订单系统 — 测试报告

## 1. 测试执行总览

| 指标 | 数值 |
|------|------|
| 总测试数 | 19 |
| 通过 | 19 |
| 失败 | 0 |
| 错误 | 0 |
| 执行时间 | 0.38s |
| 通过率 | 100% |

## 2. 测试结果明细

### 2.1 TestProductCRUD — 商品 CRUD（AC-1）

| # | 测试用例 | 结果 | 对应验收标准 |
|---|---------|------|-------------|
| 1 | test_create_product | PASSED | AC-1 |
| 2 | test_list_products | PASSED | AC-1 |
| 3 | test_get_product | PASSED | AC-1 |

### 2.2 TestOrderCRUD — 订单 CRUD（AC-2 ~ AC-5）

| # | 测试用例 | 结果 | 对应验收标准 |
|---|---------|------|-------------|
| 4 | test_create_order | PASSED | AC-2 |
| 5 | test_create_order_insufficient_stock | PASSED | AC-3 |
| 6 | test_create_order_total_calculation | PASSED | AC-4 |
| 7 | test_filter_orders | PASSED | AC-5 |

### 2.3 TestStateMachine — 状态机（AC-6 ~ AC-11）

| # | 测试用例 | 结果 | 对应验收标准 |
|---|---------|------|-------------|
| 8 | test_pay_order | PASSED | AC-6 |
| 9 | test_ship_order | PASSED | AC-7 |
| 10 | test_deliver_order | PASSED | AC-8 |
| 11 | test_illegal_pending_to_shipped | PASSED | AC-9 |
| 12 | test_illegal_paid_to_delivered | PASSED | AC-10 |
| 13 | test_delivered_cannot_be_cancelled | PASSED | AC-11 |

### 2.4 TestInventory — 库存管理（AC-12 ~ AC-14）

| # | 测试用例 | 结果 | 对应验收标准 |
|---|---------|------|-------------|
| 14 | test_pay_deducts_stock | PASSED | AC-12 |
| 15 | test_cancel_paid_restores_stock | PASSED | AC-13 |
| 16 | test_cancel_pending_no_stock_change | PASSED | AC-14 |

### 2.5 TestIdempotency — 幂等性（AC-15 ~ AC-17）

| # | 测试用例 | 结果 | 对应验收标准 |
|---|---------|------|-------------|
| 17 | test_duplicate_pay_same_key | PASSED | AC-15 |
| 18 | test_different_key_different_request | PASSED | AC-16 |
| 19 | test_missing_idempotency_key | PASSED | AC-17 |

## 3. 验收标准总结

| 验收标准 | 描述 | 结果 |
|----------|------|------|
| AC-1 | 商品 CRUD 接口正常工作 | ✅ PASS |
| AC-2 | 创建订单成功，初始状态 pending | ✅ PASS |
| AC-3 | 库存不足时创建订单返回 400 | ✅ PASS |
| AC-4 | 多商品订单总价计算正确 | ✅ PASS |
| AC-5 | 按 user_id/status 筛选订单正确 | ✅ PASS |
| AC-6 | 支付订单 pending→paid 成功 | ✅ PASS |
| AC-7 | 发货 paid→shipped 成功 | ✅ PASS |
| AC-8 | 送达 shipped→delivered 成功 | ✅ PASS |
| AC-9 | 非法跳转 pending→shipped 返回 409 | ✅ PASS |
| AC-10 | 非法跳转 paid→delivered 返回 409 | ✅ PASS |
| AC-11 | 已送达不可取消返回 409 | ✅ PASS |
| AC-12 | 付款时扣减库存 | ✅ PASS |
| AC-13 | 取消已付款订单回滚库存 | ✅ PASS |
| AC-14 | 取消 pending 订单不影响库存 | ✅ PASS |
| AC-15 | 同一 Idempotency-Key 重复付款只扣一次库存 | ✅ PASS |
| AC-16 | 不同 key 对已支付订单再次支付返回 409 | ✅ PASS |
| AC-17 | 缺少 Idempotency-Key 返回 400 | ✅ PASS |

**总计：17/17 验收标准全部通过**

## 4. 已知问题（非阻断性）

| 编号 | 问题描述 | 严重程度 | 说明 |
|------|---------|---------|------|
| N1 | SQLAlchemy `Query.get()` 废弃警告 | 低 | `Product.query.get()` 和 `Order.query.get()` 使用了 SQLAlchemy 1.x API，2.0 推荐使用 `db.session.get()`。功能不受影响 |
| N2 | `datetime.utcnow()` 废弃警告 | 低 | Python 3.12+ 标记为废弃，推荐 `datetime.now(datetime.UTC)`。功能不受影响 |

## 5. 总体评估

**测试结论：通过 ✅**

全部 19 个测试用例 100% 通过，17 项验收标准全部满足。系统功能完整，包括：
- 商品 CRUD 接口
- 订单创建、查询、筛选
- 完整的状态机（pending → paid → shipped → delivered, pending/paid → cancelled）
- 库存扣减与回滚
- 幂等付款机制
- 非法状态跳转保护
