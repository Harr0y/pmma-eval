# 方案设计文档 — T3 微型电商订单系统

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                      app.py（不可修改）                        │
│              Flask App Factory + DB 初始化                     │
│         注册 product_bp + order_bp Blueprint                  │
└──────────────────┬──────────────────────┬───────────────────┘
                   │                      │
       ┌───────────▼──────────┐  ┌────────▼──────────┐
       │  routes_product.py   │  │  routes_order.py   │
       │  (product_bp)        │  │  (order_bp)        │
       └───────────┬──────────┘  └────────┬──────────┘
                   │                      │
       ┌───────────▼──────────────────────▼──────────┐
       │              middleware.py                    │
       │  get_current_user()  check_rate_limit()     │
       └───────────────────┬─────────────────────────┘
                           │
       ┌───────────────────▼─────────────────────────┐
       │                models.py                     │
       │     User  │  Product  │  Order(+origin)      │
       └───────────────────┬─────────────────────────┘
                           │
                   ┌───────▼───────┐
                   │  SQLAlchemy   │
                   │  (SQLite)     │
                   └───────────────┘
```

## 2. 数据模型设计

### 2.1 User 模型（无需修改）
```python
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin' or 'user'
```

### 2.2 Product 模型（无需修改）
```python
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)
```

### 2.3 Order 模型（新增 origin 字段）
```python
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    origin = db.Column(db.String(20), nullable=False, default='web')  # 新增
```

**变更说明**：仅新增 `origin` 字段，其他字段保持不变。使用 `default='web'` 确保向后兼容。

## 3. API 端点设计

### 3.1 GET /products（routes_product.py）

**处理流程**：
1. 查询所有产品 `Product.query.all()`
2. 序列化为列表返回

**响应格式**：
```json
{
  "status": "ok",
  "data": [
    {"id": 1, "name": "Mouse", "price": 50.0, "stock": 5}
  ]
}
```

**无权限要求**（公开接口）

### 3.2 POST /products（routes_product.py）

**处理流程**：
1. 调用 `get_current_user()` 获取当前用户
2. 若用户为 None → 返回 401 `{"status": "error", "message": "Authentication required"}`
3. 若用户 role != 'admin' → 返回 403 `{"status": "error", "message": "Admin only"}`
4. 验证请求体包含 `name`、`price`、`stock`
5. 创建 Product 并提交
6. 返回 201 `{"status": "ok", "data": {...}}`

**错误处理**：
- 401：无 X-User-Id 或用户不存在
- 403：非 admin
- 400：缺少必填字段

### 3.3 POST /orders（routes_order.py）

**处理流程**：
1. 调用 `get_current_user()` 获取当前用户
2. 若用户为 None → 返回 401
3. 调用 `check_rate_limit(user.id)` 检查限流（仅检查，不更新时间戳）
4. 若触发限流 → 返回 429 `{"status": "error", "message": "Rate limit exceeded"}`
5. 验证请求体包含 `product_id`、`quantity`
6. 查询产品，若不存在 → 返回 400/404
7. 检查库存 `product.stock >= quantity`
8. 若库存不足 → 返回 400 `{"status": "error", "message": "Insufficient stock"}`
9. **原子性扣减库存**：使用 `UPDATE ... SET stock = stock - :qty WHERE id = :pid AND stock >= :qty`
   - 执行 UPDATE 语句，检查 affected rows
   - 若 affected rows == 0 → 库存不足（并发竞争导致），返回错误
10. 创建 Order，计算 `total_price = price * quantity`
11. 设置 `origin = request.json.get('origin', 'web')`
12. 提交事务
13. **订单创建成功后**，调用 `update_rate_limit(user.id)` 记录成功下单时间戳
14. 返回 201 `{"status": "ok", "data": {...}}`

**关键设计决策 — 库存扣减原子性**：
- 使用 `UPDATE ... WHERE stock >= quantity` 原子 SQL 语句防止并发超卖
- 选型理由：SQLite 不支持行级锁（`with_for_update()` 在 SQLite 中不生效），而 `UPDATE ... WHERE` 方案在 SQLite 中可正常工作
- 单条 SQL 同时完成"检查库存 + 扣减库存"，无需先 SELECT 再 UPDATE，避免 TOCTOU 竞态
- 若 affected rows == 0 说明并发场景下库存已被其他事务消耗，返回库存不足错误

**关键设计决策 — 限流时间戳更新时机**：
- `check_rate_limit()` 仅检查是否被限流，不更新时间戳
- 订单创建成功后才调用 `update_rate_limit()` 更新时间戳
- 避免因业务逻辑失败（如库存不足）导致时间戳被白白消耗

### 3.4 GET /orders（routes_order.py）

**处理流程**：
1. 调用 `get_current_user()` 获取当前用户
2. 若用户为 None → 返回 401
3. 若用户 role == 'admin' → `Order.query.all()`
4. 否则 → `Order.query.filter_by(user_id=user.id).all()`
5. 序列化时**必须包含 origin 字段**
6. 返回 200 `{"status": "ok", "data": [...]}`

**响应格式**：
```json
{
  "status": "ok",
  "data": [
    {"id": 1, "user_id": 2, "product_id": 1, "quantity": 1, "total_price": 50.0, "origin": "web"}
  ]
}
```

## 4. 中间件设计（middleware.py）

### 4.1 get_current_user()（需增加异常处理）

**现有逻辑保持不变，新增 X-User-Id 格式验证**：
```python
def get_current_user():
    """Get the current user from X-User-Id header.
    Returns User object or None if not found/invalid."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    try:
        uid = int(user_id)
    except (ValueError, TypeError):
        return None
    return User.query.get(uid)
```

**变更说明**：新增 `try-except` 包裹 `int(user_id)` 调用，防止非数字字符串（如 "abc"）导致未捕获的 ValueError（500 错误）。非法 X-User-Id 值视为未认证，返回 None。

### 4.2 check_rate_limit(user_id)（新增 — 仅检查，不更新时间戳）

**设计规格**：
- 使用内存字典 `_order_timestamps` 存储 `{user_id: last_successful_order_time}`
- 调用时**仅检查**当前时间与上次成功下单时间的差值
- 若差值 < 10 秒 → 返回 `False`（被限流）
- 否则返回 `True`（允许尝试下单）
- **不在此函数中更新时间戳**，时间戳由 `update_rate_limit()` 在订单成功创建后更新

```python
import time

_order_timestamps = {}

def check_rate_limit(user_id):
    """Check if user is within rate limit (1 order per 10 seconds).
    Returns True if allowed, False if rate limited.
    NOTE: Does NOT update the timestamp. Call update_rate_limit() after successful order."""
    now = time.time()
    last_time = _order_timestamps.get(user_id, 0)
    if now - last_time < 10:
        return False
    return True

def update_rate_limit(user_id):
    """Record a successful order for rate limiting purposes.
    Call this ONLY after an order is successfully created."""
    _order_timestamps[user_id] = time.time()
```

**设计考量**：
- 内存字典方案适合单进程场景，与当前 SQLite 单进程架构匹配
- 使用 `time.time()` 获取高精度时间戳
- 限流窗口为滑动窗口（从上次**成功**下单起算 10 秒）
- **关键**：时间戳仅在订单创建成功后更新，避免业务失败消耗限流窗口

## 5. 模块间接口设计

### 5.1 导入依赖关系
```
routes_product.py → from middleware import get_current_user
routes_product.py → from models import Product
routes_product.py → from app import db

routes_order.py → from middleware import get_current_user, check_rate_limit, update_rate_limit
routes_order.py → from models import Product, Order
routes_order.py → from app import db

middleware.py → from models import User
middleware.py → from flask import request
```

### 5.2 各模块导出
| 模块 | 导出 | 使用者 |
|------|------|--------|
| models.py | `User`, `Product`, `Order`, `db`(from app) | middleware, routes |
| middleware.py | `get_current_user()`, `check_rate_limit()`, `update_rate_limit()` | routes_product, routes_order |
| routes_product.py | `product_bp` (Blueprint) | app.py |
| routes_order.py | `order_bp` (Blueprint) | app.py |

## 6. 实现计划（ATU 执行顺序）

### 阶段 3：开发实现

| 执行顺序 | ATU | 文件 | 依赖 | 说明 |
|---------|-----|------|------|------|
| 1 | ATU-003 | models.py | design.md | 新增 Order.origin 字段 |
| 2 | ATU-004 | middleware.py | design.md | 新增 check_rate_limit() |
| 3 | ATU-005 | routes_product.py | ATU-003, ATU-004 | 实现 GET/POST /products |
| 4 | ATU-006 | routes_order.py | ATU-003, ATU-004 | 实现 GET/POST /orders |

**执行顺序说明**：
- ATU-003 和 ATU-004 无相互依赖，但为保持流程清晰，按顺序执行
- ATU-005 和 ATU-006 依赖 models 和 middleware，排在后面
- ATU-005 和 ATU-006 无相互依赖，但按顺序执行以降低风险

## 7. 边界条件与异常处理

### 7.1 输入验证
- `price` 和 `stock` 必须为正数
- `quantity` 必须为正整数
- `name` 不能为空字符串
- `product_id` 必须指向已存在的产品

### 7.2 并发安全
- 使用 `UPDATE ... WHERE stock >= quantity` 原子 SQL 保证库存扣减原子性（SQLite 兼容）
- 事务失败时自动回滚
- UPDATE affected rows == 0 时表示并发竞争导致库存不足

### 7.3 限流边界
- 无 `X-User-Id` 时不应触发限流检查（先检查认证）
- 用户首次下单不受限流影响
- 限流时间戳仅在订单成功创建后更新，业务失败不消耗限流窗口

### 7.4 X-User-Id 异常处理
- `X-User-Id` 为非数字字符串时，`get_current_user()` 返回 None（视为未认证）
- 避免 `int()` 转换抛出未捕获的 ValueError 导致 500 错误

## 8. 测试策略

### 8.1 基础功能测试（test_basic.py）
- 产品 CRUD 操作
- 订单创建和库存扣减
- RBAC 权限控制
- 订单查询权限过滤

### 8.2 变更需求测试（test_change.py）
- origin 字段默认值和自定义值
- 限流 429 响应
- 不同用户限流隔离
- 库存原子性（无负库存）
- 零库存下单失败
