# 测试报告 — T3 微型电商订单系统

## 测试执行概况

| 指标 | 数值 |
|------|------|
| 测试总数 | 19 |
| 通过数 | 19 |
| 失败数 | 0 |
| 通过率 | **100%** |
| 执行时间 | 0.33s |
| 警告数 | 40（SQLAlchemy LegacyAPIWarning，非功能性） |

## 测试执行输出

```
tests/test_basic.py::TestProductManagement::test_admin_can_create_product PASSED
tests/test_basic.py::TestProductManagement::test_user_cannot_create_product PASSED
tests/test_basic.py::TestProductManagement::test_list_products PASSED
tests/test_basic.py::TestProductManagement::test_no_user_id_returns_error PASSED
tests/test_basic.py::TestOrderSystem::test_user_can_create_order PASSED
tests/test_basic.py::TestOrderSystem::test_order_deducts_stock PASSED
tests/test_basic.py::TestOrderSystem::test_insufficient_stock PASSED
tests/test_basic.py::TestOrderSystem::test_admin_sees_all_orders PASSED
tests/test_basic.py::TestOrderSystem::test_user_sees_only_own_orders PASSED
tests/test_basic.py::TestOrderSystem::test_order_total_price PASSED
tests/test_basic.py::TestOrderSystem::test_order_nonexistent_product PASSED
tests/test_basic.py::TestRBAC::test_user_cannot_create_product PASSED
tests/test_basic.py::TestRBAC::test_admin_can_create_product PASSED
tests/test_change.py::TestOrderOrigin::test_order_default_origin PASSED
tests/test_change.py::TestOrderOrigin::test_order_custom_origin PASSED
tests/test_change.py::TestRateLimiting::test_rapid_order_blocked PASSED
tests/test_change.py::TestRateLimiting::test_different_users_not_limited PASSED
tests/test_change.py::TestAtomicStock::test_stock_no_negative PASSED
tests/test_change.py::TestAtomicStock::test_zero_stock_order_fails PASSED

19 passed, 0 failed, 40 warnings in 0.33s
```

## 验收标准对照

### AC-01：产品管理 ✅ 通过

| 验收项 | 对应测试 | 状态 |
|--------|----------|------|
| admin 可以成功创建产品，返回 status "ok" | test_admin_can_create_product | PASS |
| 普通用户创建产品返回 403 | test_user_cannot_create_product | PASS |
| 缺少 X-User-Id 创建产品返回 400/401/403 | test_no_user_id_returns_error | PASS |
| GET /products 返回所有产品列表 | test_list_products | PASS |
| 无产品时返回空列表 | 无独立测试；实现层面 `Product.query.all()` 空结果返回 `[]`，逻辑正确 | **未覆盖（依赖实现保证）** |

### AC-02：订单系统 ✅ 通过

| 验收项 | 对应测试 | 状态 |
|--------|----------|------|
| 用户可以成功下单，返回 status "ok" | test_user_can_create_order | PASS |
| 下单后库存正确扣减 | test_order_deducts_stock | PASS |
| 库存不足时返回 status "error"，库存不被扣减 | test_insufficient_stock | PASS |
| 订单 total_price = price × quantity 计算正确 | test_order_total_price | PASS |
| 购买不存在的产品返回 400/404 | test_order_nonexistent_product | PASS |
| admin 查看订单可看到所有订单 | test_admin_sees_all_orders | PASS |
| 普通用户查看订单只能看到自己的 | test_user_sees_only_own_orders | PASS |

### AC-03：RBAC 权限控制 ✅ 通过

| 验收项 | 对应测试 | 状态 |
|--------|----------|------|
| 普通用户不能创建产品（403） | TestRBAC::test_user_cannot_create_product | PASS |
| admin 可以创建产品（200/201） | TestRBAC::test_admin_can_create_product | PASS |

> 注：TestRBAC 与 TestProductManagement 中存在功能重复的测试用例（test_user_cannot_create_product 和 test_admin_can_create_product 各出现两次），属于测试冗余但不影响正确性。

### AC-04：渠道追溯 ✅ 通过（部分依赖实现保证）

| 验收项 | 对应测试 | 状态 |
|--------|----------|------|
| 下单时未指定 origin，默认为 'web' | test_order_default_origin | PASS |
| 下单时可以指定 origin（如 'app'） | test_order_custom_origin | PASS |
| 订单查询接口返回 origin 字段 | 无独立测试；实现层面 `_serialize_order()` 始终包含 origin 字段 | **未覆盖（依赖实现保证）** |

### AC-05：限流 ✅ 通过

| 验收项 | 对应测试 | 状态 |
|--------|----------|------|
| 同一用户 10 秒内快速下两单，第二单返回 429 | test_rapid_order_blocked | PASS |
| 不同用户不受限流影响 | test_different_users_not_limited | PASS |

### AC-06：原子库存 ✅ 通过（部分依赖实现保证）

| 验收项 | 对应测试 | 状态 |
|--------|----------|------|
| 库存不能变为负数 | test_stock_no_negative | PASS |
| 库存为 0 的商品不能下单 | test_zero_stock_order_fails | PASS |
| 并发下单不会导致超卖 | 无并发测试；实现层面使用 `UPDATE ... WHERE stock >= quantity` 条件 UPDATE 方案，SQL 层面原子性保证 | **未覆盖（依赖实现保证）** |

> 注：SQLite 内存数据库在单线程 pytest 环境下难以真正模拟并发超卖场景。条件 UPDATE 方案在 SQLite 中是原子操作，且若迁移至 MySQL/PostgreSQL 等支持真正并发的数据库，该方案同样有效。

## 覆盖率总结

| 验收标准 | 显式测试覆盖 | 依赖实现保证 | 总体 |
|----------|-------------|-------------|------|
| AC-01 产品管理 | 4/5 | 1/5 | ✅ |
| AC-02 订单系统 | 7/7 | 0/7 | ✅ |
| AC-03 RBAC | 2/2 | 0/2 | ✅ |
| AC-04 渠道追溯 | 2/3 | 1/3 | ✅ |
| AC-05 限流 | 2/2 | 0/2 | ✅ |
| AC-06 原子库存 | 2/3 | 1/3 | ✅ |
| **合计** | **19/22** | **3/22** | **✅** |

## 已知技术债务

1. **SQLAlchemy LegacyAPIWarning**（40 个）：`Query.get()` 在 SQLAlchemy 2.0 中已标记为废弃，建议后续迁移至 `db.session.get()`。影响文件：middleware.py、routes_order.py。不影响功能正确性。

2. **origin 参数类型验证**：当前实现未显式校验 origin 是否为字符串类型，但数据库层 `String(50)` 提供了兜底约束。

3. **测试冗余**：TestRBAC 与 TestProductManagement 中存在 2 个功能完全重复的测试用例，建议后续去重。

4. **测试环境差异风险**：当前测试使用 SQLite 内存数据库，与生产环境可能使用的 MySQL/PostgreSQL 存在 SQL 方言差异。建议后续增加 CI 环境下的多数据库兼容性测试。

## 结论

**系统符合交付标准。** 19/19 测试用例全部 PASSED，22 项验收条目中 19 项有显式测试覆盖，3 项依赖实现层面的保证（空列表返回、GET /orders 返回 origin、并发超卖防护）。所有验收条目的实现均已通过代码审查确认正确。
