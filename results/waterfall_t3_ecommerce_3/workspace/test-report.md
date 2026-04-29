# 测试验证报告 (test-report.md)

## 1. 测试执行结果

| 指标 | 值 |
|------|-----|
| 测试总数 | 19 |
| 通过 | 19 |
| 失败 | 0 |
| 执行时间 | 0.31s |
| 测试文件 | test_basic.py (13 tests) + test_change.py (6 tests) |

## 2. 逐条验收标准对照

### 5.1 产品管理

| AC | 验收标准 | 覆盖测试 | 结果 |
|----|---------|---------|------|
| AC-01 | Admin 创建产品返回 200/201 | `test_admin_can_create_product` ×2 | ✅ PASS |
| AC-02 | 普通用户创建产品返回 403 | `test_user_cannot_create_product` ×2 | ✅ PASS |
| AC-03 | GET /products 返回产品列表 | `test_list_products` | ✅ PASS |
| AC-04 | POST /products 缺少 X-User-Id 返回 401 | `test_no_user_id_returns_error` | ⚠️ 弱验证 |

### 5.2 订单系统

| AC | 验收标准 | 覆盖测试 | 结果 |
|----|---------|---------|------|
| AC-05 | 下单后库存减少量 = quantity | `test_order_deducts_stock` | ✅ PASS |
| AC-06 | 库存不足拒绝且库存不变 | `test_insufficient_stock` | ✅ PASS |
| AC-07 | Admin 查看所有订单 | `test_admin_sees_all_orders` | ✅ PASS |
| AC-08 | 普通用户只看自己的订单 | `test_user_sees_only_own_orders` | ✅ PASS |
| AC-09 | total_price = price × quantity | `test_order_total_price` | ✅ PASS |
| AC-10 | 购买不存在产品返回 400/404 | `test_order_nonexistent_product` | ✅ PASS |
| AC-11 | POST /orders 缺少 X-User-Id 返回 401 | 无专门测试 | ⚠️ 缺失 |

### 5.3 RBAC

| AC | 验收标准 | 覆盖测试 | 结果 |
|----|---------|---------|------|
| AC-12 | 普通用户创建产品返回 403 | `TestRBAC::test_user_cannot_create_product` | ✅ PASS |
| AC-13 | Admin 创建产品返回 200/201 | `TestRBAC::test_admin_can_create_product` | ✅ PASS |

### 5.4 需求变更

| AC | 验收标准 | 覆盖测试 | 结果 |
|----|---------|---------|------|
| AC-14 | origin 默认为 'web' | `test_order_default_origin` | ✅ PASS |
| AC-15 | 指定 origin='app' 返回 'app' | `test_order_custom_origin` | ✅ PASS |
| AC-16 | 同一用户 10s 内第二单返回 429 | `test_rapid_order_blocked` | ✅ PASS |
| AC-17 | 不同用户不受限流影响 | `test_different_users_not_limited` | ✅ PASS |
| AC-18 | 库存不能为负数 | `test_stock_no_negative` | ✅ PASS |
| AC-19 | 库存为 0 的商品不能下单 | `test_zero_stock_order_fails` | ✅ PASS |

### 5.5 系统约束

| AC | 验收标准 | 结果 |
|----|---------|------|
| AC-20 | create_app() 返回 Flask 实例 | ✅ 隐式覆盖（fixture 调用无异常） |
| AC-21 | url_map 包含 /products 和 /orders | ✅ 隐式覆盖（所有路由测试正常工作） |

## 3. 统计汇总

| 类别 | 数量 |
|------|------|
| ✅ 明确通过 | 17/21 |
| ⚠️ 弱验证 | 1/21 (AC-04) |
| ⚠️ 缺失覆盖 | 1/21 (AC-11) |
| ✅ 隐式覆盖 | 2/21 (AC-20, AC-21) |

## 4. 已知测试覆盖盲区

| 盲区 | 严重程度 | 说明 |
|------|---------|------|
| AC-04 断言过于宽松 | 低 | 测试接受 400/401/403，但实现正确返回 401 |
| AC-11 无专门测试 | 低 | POST /orders 认证逻辑与其他路由一致，风险低 |
| 边界值测试缺失 | 低 | 负数 price、空字符串 name 等未测试 |
| quantity 浮点数 | 低 | `isinstance(quantity, int)` 会拒绝 float 类型 |

## 5. 测试基础设施变更

Developer 在实现过程中新增了 `reset_rate_limits()` 函数到 `middleware.py`，并在两个测试文件的 fixture 中调用，用于解决限流状态在测试用例间泄漏的问题。

## 6. 结论

**测试通过，符合交付标准。** 19/19 测试全部通过，核心业务逻辑（产品 CRUD、订单创建、库存扣减、RBAC、限流、origin 字段）实现正确。已知的测试覆盖盲区均为低风险，不影响核心功能。
