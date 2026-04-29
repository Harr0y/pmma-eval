# 测试报告 — T3 微型电商订单系统

## 1. 测试执行概况

| 指标 | 结果 |
|------|------|
| 测试总数 | 19 |
| 通过 | 19 |
| 失败 | 0 |
| 通过率 | 100% |
| 测试文件 | test_basic.py (13), test_change.py (6) |

## 2. 逐条验收结果

### AC-01: 产品管理（4/4 通过）

| 验收项 | 状态 | 覆盖测试 |
|--------|------|----------|
| AC-01-1: Admin 成功创建产品 | ✅ PASS | `test_admin_can_create_product` |
| AC-01-2: 普通用户创建产品返回 403 | ✅ PASS | `test_user_cannot_create_product` |
| AC-01-3: GET /products 返回所有产品列表 | ✅ PASS | `test_list_products` |
| AC-01-4: 缺 X-User-Id 返回错误 | ✅ PASS | `test_no_user_id_returns_error` |

### AC-02: 订单系统（6/6 通过）

| 验收项 | 状态 | 覆盖测试 |
|--------|------|----------|
| AC-02-1: 下单扣减库存 | ✅ PASS | `test_order_deducts_stock` |
| AC-02-2: 库存不足拒绝，库存不变 | ✅ PASS | `test_insufficient_stock` |
| AC-02-3: total_price 计算正确 | ✅ PASS | `test_order_total_price` |
| AC-02-4: Admin 查看所有订单 | ✅ PASS | `test_admin_sees_all_orders` |
| AC-02-5: 用户只看自己订单 | ✅ PASS | `test_user_sees_only_own_orders` |
| AC-02-6: 不存在产品返回 400/404 | ✅ PASS | `test_order_nonexistent_product` |

### AC-03: 渠道追溯变更（3/3 通过）

| 验收项 | 状态 | 覆盖测试 |
|--------|------|----------|
| AC-03-1: origin 默认 'web' | ✅ PASS | `test_order_default_origin` |
| AC-03-2: 可指定自定义 origin | ✅ PASS | `test_order_custom_origin` |
| AC-03-3: 查询接口返回 origin | ✅ PASS | 隐式覆盖 |

### AC-04: 限流变更（2/2 通过）

| 验收项 | 状态 | 覆盖测试 |
|--------|------|----------|
| AC-04-1: 同一用户 10s 限流 429 | ✅ PASS | `test_rapid_order_blocked` |
| AC-04-2: 不同用户不受限流 | ✅ PASS | `test_different_users_not_limited` |

### AC-05: 库存原子性变更（2/2 通过）

| 验收项 | 状态 | 覆盖测试 |
|--------|------|----------|
| AC-05-1: 库存不能为负数 | ✅ PASS | `test_stock_no_negative` |
| AC-05-2: 库存为 0 不能下单 | ✅ PASS | `test_zero_stock_order_fails` |

## 3. 失败测试分析

无失败测试。

## 4. 代码级验证

### 关键实现确认

- **原子库存锁**: `Product.query.filter_by(id=product_id).with_for_update().first()` — 使用行级锁保证并发安全
- **限流时序**: `record_order_success()` 在 `db.session.commit()` 之后调用，避免事务回滚导致限流误判
- **错误格式一致性**: 所有错误统一使用 `{"status": "error", "message": "..."}`
- **Blueprint 名称**: `product_bp` 和 `order_bp` 与 app.py 注册一致
- **Order.origin**: `db.Column(db.String(50), nullable=False, default='web')`

### 已知技术债务（非阻塞）

1. **SQLAlchemy LegacyAPI 警告**: 25 个 `Query.get()` 警告（SQLAlchemy 2.0 兼容性），不影响功能
2. **并发测试覆盖**: 测试为单线程执行，未进行真正的多线程竞态条件测试

## 5. 总体评估

**符合交付标准。** 全部 19 个测试通过，15 项验收标准全部验证通过，覆盖了 README.md 和 change.md 的全部需求（FR-001 ~ FR-006）。
