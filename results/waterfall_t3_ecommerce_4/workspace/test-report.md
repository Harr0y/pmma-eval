# 测试验证报告 — T3 微型电商订单系统

## 1. 测试执行摘要

| 指标 | 数值 |
|------|------|
| 测试总数 | 19 |
| 通过 | 19 |
| 失败 | 0 |
| 通过率 | **100%** |
| 验收标准满足率 | **22/22 (100%)** |
| 执行时间 | 0.33s |

## 2. 测试运行结果

### test_basic.py（13 个测试）

| 测试用例 | 状态 | 对应验收标准 |
|---------|------|-------------|
| TestProductManagement::test_admin_can_create_product | ✅ PASSED | AC-1.1 |
| TestProductManagement::test_user_cannot_create_product | ✅ PASSED | AC-1.2 |
| TestProductManagement::test_list_products | ✅ PASSED | AC-1.4, AC-1.5 |
| TestProductManagement::test_no_user_id_returns_error | ✅ PASSED | AC-1.3 |
| TestOrderSystem::test_user_can_create_order | ✅ PASSED | AC-2.1 |
| TestOrderSystem::test_order_deducts_stock | ✅ PASSED | AC-2.2 |
| TestOrderSystem::test_insufficient_stock | ✅ PASSED | AC-2.3, AC-2.4 |
| TestOrderSystem::test_admin_sees_all_orders | ✅ PASSED | AC-2.5 |
| TestOrderSystem::test_user_sees_only_own_orders | ✅ PASSED | AC-2.6 |
| TestOrderSystem::test_order_total_price | ✅ PASSED | AC-2.7 |
| TestOrderSystem::test_order_nonexistent_product | ✅ PASSED | AC-2.8 |
| TestRBAC::test_user_cannot_create_product | ✅ PASSED | AC-1.2 |
| TestRBAC::test_admin_can_create_product | ✅ PASSED | AC-1.1 |

### test_change.py（6 个测试）

| 测试用例 | 状态 | 对应验收标准 |
|---------|------|-------------|
| TestOrderOrigin::test_order_default_origin | ✅ PASSED | AC-3.1 |
| TestOrderOrigin::test_order_custom_origin | ✅ PASSED | AC-3.2 |
| TestRateLimiting::test_rapid_order_blocked | ✅ PASSED | AC-3.3 |
| TestRateLimiting::test_different_users_not_limited | ✅ PASSED | AC-3.4 |
| TestAtomicStock::test_stock_no_negative | ✅ PASSED | AC-3.5 |
| TestAtomicStock::test_zero_stock_order_fails | ✅ PASSED | AC-3.6 |

## 3. 验收标准对照

### AC-1: 产品管理

| 验收条目 | 结果 |
|---------|------|
| Admin 可以成功创建产品（200/201） | ✅ 通过 |
| 普通用户创建产品被拒绝（403） | ✅ 通过 |
| 缺少 X-User-Id 创建产品被拒绝（400/401） | ✅ 通过 |
| 所有人可以列出产品 | ✅ 通过 |
| 产品列表返回正确的数据格式 | ✅ 通过 |

### AC-2: 订单系统

| 验收条目 | 结果 |
|---------|------|
| 用户可以成功下单（200/201） | ✅ 通过 |
| 下单时库存正确扣减 | ✅ 通过 |
| 库存不足时下单失败（status: "error"） | ✅ 通过 |
| 库存不足时库存不变 | ✅ 通过 |
| Admin 查看所有订单 | ✅ 通过 |
| 普通用户只看自己的订单 | ✅ 通过 |
| 订单 total_price 计算正确 | ✅ 通过 |
| 购买不存在的产品返回 400/404 | ✅ 通过 |

### AC-3: 需求变更

| 验收条目 | 结果 |
|---------|------|
| 下单不指定 origin 时默认为 'web' | ✅ 通过 |
| 下单可自定义 origin | ✅ 通过 |
| 同一用户 10 秒内第二单返回 429 | ✅ 通过 |
| 不同用户不受限流影响 | ✅ 通过 |
| 库存不能为负数 | ✅ 通过 |
| 库存为 0 的商品不能下单 | ✅ 通过 |

### AC-4: 系统约束

| 验收条目 | 结果 |
|---------|------|
| app.py 未被修改 | ✅ 通过 |
| Blueprint 名称与 app.py 注册一致 | ✅ 通过 |
| create_app() 正常启动 | ✅ 通过 |
| 所有模块间 import 正确 | ✅ 通过 |

## 4. 已知问题

| 级别 | 问题描述 | 影响 | 建议 |
|------|---------|------|------|
| 低 | SQLAlchemy `Query.get()` 产生 LegacyAPIWarning（40 个） | 仅警告，不影响功能 | 后续迭代替换为 `Session.get()` |
| 低 | routes_order.py 第 93 行使用 `request.json` 而非已解析的 `body` 变量 | 多余的重复 JSON 解析，不影响功能 | 改为 `body.get('origin', 'web')` |

## 5. 总体结论

**符合交付标准**。所有 19 个测试用例通过，22 项验收标准全部满足。无阻塞性问题。
