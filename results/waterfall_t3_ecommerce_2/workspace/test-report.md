# 测试报告 — T3 微型电商订单系统

## 1. 测试结果总览

| 指标 | 结果 |
|------|------|
| 测试总数 | 19 |
| 通过 | 19 |
| 失败 | 0 |
| 跳过 | 0 |
| 通过率 | **100%** |

## 2. 基础功能验收（test_basic.py）— 13/13 通过

| # | 验收标准 | 测试方法 | 结果 |
|---|---------|---------|------|
| 1 | 管理员可创建产品 | `TestProductManagement::test_admin_can_create_product` | ✅ PASS |
| 2 | 普通用户不能创建产品（403） | `TestProductManagement::test_user_cannot_create_product` | ✅ PASS |
| 3 | 列出所有产品 | `TestProductManagement::test_list_products` | ✅ PASS |
| 4 | 缺少 X-User-Id 创建产品失败 | `TestProductManagement::test_no_user_id_returns_error` | ✅ PASS |
| 5 | 用户可下单 | `TestOrderSystem::test_user_can_create_order` | ✅ PASS |
| 6 | 下单扣减库存 | `TestOrderSystem::test_order_deducts_stock` | ✅ PASS |
| 7 | 库存不足下单失败，库存不变 | `TestOrderSystem::test_insufficient_stock` | ✅ PASS |
| 8 | 管理员查看所有订单 | `TestOrderSystem::test_admin_sees_all_orders` | ✅ PASS |
| 9 | 普通用户只看自己订单 | `TestOrderSystem::test_user_sees_only_own_orders` | ✅ PASS |
| 10 | 订单总价计算正确 | `TestOrderSystem::test_order_total_price` | ✅ PASS |
| 11 | 购买不存在产品失败 | `TestOrderSystem::test_order_nonexistent_product` | ✅ PASS |
| 12 | RBAC: 普通用户不能创建产品 | `TestRBAC::test_user_cannot_create_product` | ✅ PASS |
| 13 | RBAC: 管理员可创建产品 | `TestRBAC::test_admin_can_create_product` | ✅ PASS |

## 3. 变更功能验收（test_change.py）— 6/6 通过

| # | 验收标准 | 测试方法 | 结果 |
|---|---------|---------|------|
| 1 | 下单默认 origin 为 'web' | `TestOrderOrigin::test_order_default_origin` | ✅ PASS |
| 2 | 下单可指定自定义 origin | `TestOrderOrigin::test_order_custom_origin` | ✅ PASS |
| 3 | 同一用户 10 秒内快速下两单返回 429 | `TestRateLimiting::test_rapid_order_blocked` | ✅ PASS |
| 4 | 不同用户不受限流影响 | `TestRateLimiting::test_different_users_not_limited` | ✅ PASS |
| 5 | 库存不能为负数 | `TestAtomicStock::test_stock_no_negative` | ✅ PASS |
| 6 | 库存为 0 的商品不能下单 | `TestZeroStockOrder::test_zero_stock_order_fails` | ✅ PASS |

## 4. 非功能性需求验证

| 需求项 | 验证结果 |
|--------|----------|
| `create_app()` 正常启动 | ✅ 所有 19 个测试均通过应用创建 |
| 模块间 import 链不断裂 | ✅ 全链路 import 正常 |
| 错误响应统一格式 `{"status": "error", ...}` | ✅ 所有错误路径均符合 |

## 5. 已知非阻塞问题

- SQLAlchemy `LegacyAPIWarning`：`Query.get()` 在 SQLAlchemy 2.0 中已弃用。涉及 `middleware.py` 第 34 行和测试文件中的 `Product.query.get()` 调用。不影响功能正确性，建议后续迁移至 `db.session.get()`。

## 6. 结论

**符合最终交付标准。** 19/19 测试全部通过，覆盖了 requirements.md 第 5 节的全部 19 项验收标准。
