# 交付总结 — T3 微型电商订单系统

## 1. 项目概述

基于 Flask + SQLAlchemy 的多模块微型电商系统，包含产品管理、订单系统、用户 RBAC 权限控制、限流和原子库存扣减。使用瀑布方法管理开发流程，所有 5 个阶段均通过 Reviewer 门控审批。

## 2. 实现的功能列表

### 2.1 数据模型（models.py）
- User 模型：id, username, role + to_dict()
- Product 模型：id, name, price, stock + to_dict()
- Order 模型：id, user_id, product_id, quantity, total_price, **origin**（默认 'web'）+ to_dict()

### 2.2 认证中间件（middleware.py）
- `get_current_user()`: 从 X-User-Id header 获取用户
- `check_rate_limit(user_id, window=10)`: 限流检查，返回 (allowed, remaining)
- `record_order(user_id)`: 记录成功下单时间
- `rate_limit_order`: check_rate_limit 的别名
- `reset_rate_limits()`: 测试辅助函数

### 2.3 产品管理（routes_product.py）
- `GET /products`: 列出所有产品（无需认证）
- `POST /products`: 创建产品（Admin only, 401/403/400 错误处理）

### 2.4 订单系统（routes_order.py）
- `POST /orders`: 创建订单（认证→限流429→验证→原子库存→创建订单→记录限流）
  - origin 参数可选，默认 'web'
  - total_price = product.price * quantity
  - 原子库存扣减：SQL 条件更新，防止超卖
- `GET /orders`: 查看订单（admin 看全部，user 看自己）

## 3. 测试覆盖情况

| 指标 | 结果 |
|------|------|
| 测试总数 | 19 |
| 通过 | 19 |
| 失败 | 0 |
| 通过率 | **100%** |

### 测试分布

| 模块 | 测试数 | 覆盖内容 |
|------|--------|----------|
| 产品管理 (test_basic.py) | 6 | 创建/列表/RBAC/错误处理 |
| 订单系统 (test_basic.py) | 7 | 下单/库存/总价/权限/不存在产品 |
| RBAC (test_basic.py) | 2 | admin vs user 权限 |
| Origin 字段 (test_change.py) | 2 | 默认值/自定义值 |
| 限流 (test_change.py) | 2 | 同用户限流/不同用户不限 |
| 原子库存 (test_change.py) | 2 | 不超卖/零库存拒绝 |

## 4. 需求变更处理

项目执行中途接收到 change.md 的需求变更，通过模块化设计顺利集成：

| 变更 | 影响文件 | 处理方式 |
|------|----------|----------|
| Order origin 字段 | models.py, routes_order.py | ATU-003 新增字段，ATU-006 传递参数 |
| 10 秒限流 | middleware.py, routes_order.py | ATU-004 实现限流，ATU-006 集成调用 |
| 原子库存扣减 | routes_order.py | ATU-006 使用 SQL 条件更新 |

## 5. 修改的文件清单

| 文件 | 操作 | ATU |
|------|------|-----|
| `starter/models.py` | 修改 | ATU-003 |
| `starter/middleware.py` | 修改 | ATU-004 |
| `starter/routes_product.py` | 修改 | ATU-005 |
| `starter/routes_order.py` | 修改 | ATU-006 |
| `tests/conftest.py` | 新增 | ATU-006 |
| `app.py` | **未修改** | — |

## 6. 已知问题与待改进项

1. **SQLAlchemy LegacyAPIWarning**: `Query.get()` 在 SQLAlchemy 2.0 中已弃用。建议将 `User.query.get()` 和 `Product.query.get()` 迁移至 `db.session.get()`。
2. **限流存储**: 当前使用进程内字典，不支持多进程/分布式部署。如需水平扩展，建议迁移至 Redis。
3. **product_id 类型验证**: 订单路由未对 product_id 做类型验证（依赖 SQLite 隐式转换）。建议后续补充。
4. **会话持久化**: 当前使用内存 session，重启后丢失（属于项目已知限制）。

## 7. 瀑布流程执行记录

| 阶段 | ATU | 状态 | Reviewer 门控 |
|------|-----|------|---------------|
| 1. 需求分析 | ATU-001 | ✅ Done | ✅ 通过 |
| 2. 方案设计 | ATU-002 | ✅ Done | ✅ 通过 |
| 3. 开发实现 | ATU-003~006 | ✅ Done | ✅ 全部通过 |
| 4. 测试验证 | ATU-007 | ✅ Done | ✅ 通过（19/19） |
| 5. 最终交付 | ATU-008 | ✅ Done | ✅ 验收 |

**无返工，所有 ATU 一次通过。**
