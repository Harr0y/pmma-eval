# 设计文档 — T3 微型电商订单系统

## 1. 数据库表设计

### 1.1 User 表

```python
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin' or 'user'
```

**无需修改**，已有定义满足所有需求。

### 1.2 Product 表

```python
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)
```

**无需修改**，已有定义满足所有需求。

### 1.3 Order 表（需变更）

```python
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    origin = db.Column(db.String(50), nullable=False, default='web')  # CHG-001 新增
```

**变更点**：新增 `origin` 字段，类型 `String(50)`，非空，默认值 `'web'`。

## 2. API 端点设计

### 2.1 `GET /products` — 列出所有产品

| 项目 | 说明 |
|------|------|
| 认证 | 不需要 |
| 权限 | 无 |
| 成功响应 (200) | `{"status": "ok", "data": [{"id", "name", "price", "stock"}, ...]}` |

**实现逻辑**：
1. `Product.query.all()` 获取所有产品
2. 序列化为字典列表
3. 返回统一格式

### 2.2 `POST /products` — 创建产品

| 项目 | 说明 |
|------|------|
| 认证 | 需要 `X-User-Id` |
| 权限 | Admin only |
| 请求体 | `{"name": str, "price": float, "stock": int}` |
| 成功 (200/201) | `{"status": "ok", "data": {"id", "name", "price", "stock"}}` |
| 错误 (401) | 无 `X-User-Id` 或用户不存在 |
| 错误 (403) | 非 admin |
| 错误 (400) | 缺少必填字段 |

**实现逻辑**：
1. 调用 `get_current_user()` 获取用户
2. 若用户为 None → 401
3. 若用户 role ≠ 'admin' → 403
4. 验证请求体字段完整性（name, price, stock）
5. 创建 Product 并 commit
6. 返回 201 + 产品数据

### 2.3 `POST /orders` — 创建订单

| 项目 | 说明 |
|------|------|
| 认证 | 需要 `X-User-Id` |
| 权限 | 任何已认证用户 |
| 请求体 | `{"product_id": int, "quantity": int, "origin": str（可选）}` |
| 成功 (200/201) | `{"status": "ok", "data": {"id", "user_id", "product_id", "quantity", "total_price", "origin"}}` |
| 错误 (401) | 无 `X-User-Id` 或用户不存在 |
| 错误 (400) | 请求参数无效（product_id/quantity 类型错误、quantity ≤ 0） |
| 错误 (404) | 产品不存在 |
| 错误 ({"status": "error"}) | 库存不足 |
| 错误 (429) | 触发限流 |

**实现逻辑**：
1. 调用 `get_current_user()` 获取用户
2. 若用户为 None → 401
3. **限流检查**：调用 `check_rate_limit(user.id)` → 若被限流返回 429
4. 获取并验证请求参数：
   - `product_id` 必须为正整数
   - `quantity` 必须为正整数（> 0）
   - `origin` 可选，默认 `'web'`
   - 参数缺失或无效 → 400
5. 查询 Product → 若不存在返回 404
6. **原子库存扣减**（详见 §3.2）：使用条件 UPDATE 保证原子性
7. 计算 `total_price = product.price * quantity`
8. 创建 Order 记录并 commit
9. **仅在 commit 成功后**调用 `mark_order_placed(user.id)` 更新限流标记
10. 返回订单数据

### 2.4 `GET /orders` — 查看订单

| 项目 | 说明 |
|------|------|
| 认证 | 需要 `X-User-Id` |
| 权限 | Admin 看全部，普通用户看自己的 |
| 成功 (200) | `{"status": "ok", "data": [{"id", "user_id", "product_id", "quantity", "total_price", "origin"}, ...]}` |
| 错误 (401) | 无 `X-User-Id` 或用户不存在 |

**实现逻辑**：
1. 调用 `get_current_user()` 获取用户
2. 若用户为 None → 401
3. 若用户 role == 'admin' → `Order.query.all()`
4. 否则 → `Order.query.filter_by(user_id=user.id).all()`
5. 序列化并返回

## 3. 关键算法逻辑

### 3.1 限流算法（middleware.py）

```python
import time

# 进程内存存储：{user_id: last_order_timestamp}
_rate_limit_store = {}

def check_rate_limit(user_id):
    """检查用户是否在 10 秒内已下过单。返回 True 表示被限流。"""
    now = time.time()
    last_time = _rate_limit_store.get(user_id)
    if last_time and (now - last_time) < 10:
        return True  # 被限流
    return False  # 未被限流

def mark_order_placed(user_id):
    """记录用户下单时间（仅在订单成功创建后调用）。"""
    _rate_limit_store[user_id] = time.time()

def clear_rate_limits():
    """清理所有限流记录（用于测试隔离）。"""
    _rate_limit_store.clear()
```

**关键设计决策**：
- 限流标记必须在订单**成功创建后**才设置（`mark_order_placed`）
- 如果下单因库存不足、参数无效等原因失败，**不应**更新限流时间戳（失败的下单不消耗限流配额）
- 不同用户使用不同的 `user_id` 作为 key，天然隔离
- 提供 `clear_rate_limits()` 函数用于测试 fixture 中清理全局状态，避免测试间状态泄漏
- **内存清理说明**：`_rate_limit_store` 会随时间增长，但由于本项目规模有限（单进程、少量用户），无需额外清理机制。若需扩展，可定期清理超过 10 秒的旧条目。

### 3.2 原子库存扣减（routes_order.py）

**⚠️ SQLite 兼容方案**：本项目使用 SQLite 数据库，**不支持** `SELECT ... FOR UPDATE` 行级锁。因此采用**条件 UPDATE** 方案保证原子性：

```python
# 方案：使用条件 UPDATE 实现原子库存扣减
# 在单个 UPDATE 语句中同时完成库存检查和扣减
from sqlalchemy import update

result = db.session.execute(
    update(Product)
    .where(Product.id == product_id, Product.stock >= quantity)
    .values(stock=Product.stock - quantity)
)

if result.rowcount == 0:
    # 要么产品不存在，要么库存不足
    product = Product.query.get(product_id)
    if product is None:
        return {"status": "error", "message": "Product not found"}, 404
    else:
        return {"status": "error", "message": "Insufficient stock"}, 400

# UPDATE 成功，创建订单
order = Order(
    user_id=user.id,
    product_id=product_id,
    quantity=quantity,
    total_price=product.price * quantity,
    origin=origin
)
db.session.add(order)
db.session.commit()
```

**关键设计决策**：
- 使用 `UPDATE ... WHERE stock >= quantity` 单条 SQL 语句同时完成库存检查和扣减
- SQLite 的 `UPDATE` 语句本身是原子的，不会出现竞态条件
- 通过检查 `result.rowcount` 判断是否成功：`rowcount == 0` 表示产品不存在或库存不足
- 如果 UPDATE 成功但后续创建 Order 失败，事务回滚，库存也会恢复（同一事务）
- 此方案完全兼容 SQLite，无需额外依赖

### 3.3 输入验证规则

| 参数 | 验证规则 | 错误响应 |
|------|----------|----------|
| `product_id` | 必须存在且为正整数 | 400（缺失/无效）或 404（不存在） |
| `quantity` | 必须为正整数（> 0） | 400 |
| `origin` | 可选，若提供必须为字符串 | 使用默认值 `'web'` |
| `name`（产品） | 必须为非空字符串 | 400 |
| `price`（产品） | 必须为数值类型 | 400 |
| `stock`（产品） | 必须为非负整数 | 400 |

### 3.4 订单序列化辅助函数

```python
def _serialize_order(order):
    return {
        'id': order.id,
        'user_id': order.user_id,
        'product_id': order.product_id,
        'quantity': order.quantity,
        'total_price': order.total_price,
        'origin': order.origin
    }
```

## 4. 模块间依赖关系

```
models.py (数据模型)
    ↑ 导入
    ├── routes_product.py (产品路由)
    ├── routes_order.py (订单路由)
    └── middleware.py (认证/限流中间件)

middleware.py (认证/限流)
    ↑ 导入
    ├── routes_product.py (需要 get_current_user)
    └── routes_order.py (需要 get_current_user + check_rate_limit + mark_order_placed)

app.py (组装) — 不可修改
    → 导入 product_bp, order_bp, User, Product, Order
```

## 5. 实现计划（ATU 拆分和执行顺序）

> ATU-001（需求分析）和 ATU-002（方案设计）为管理阶段，已在 state.json 中定义。

### ATU-003：数据模型实现
- **文件**：`starter/models.py`
- **变更**：Order 模型新增 `origin = db.Column(db.String(50), nullable=False, default='web')`
- **预估行数**：~1 行新增

### ATU-004：认证中间件完善
- **文件**：`starter/middleware.py`
- **变更**：
  - 新增 `import time`
  - 新增 `_rate_limit_store = {}` 字典
  - 新增 `check_rate_limit(user_id)` 函数
  - 新增 `mark_order_placed(user_id)` 函数
  - 新增 `clear_rate_limits()` 函数
- **预估行数**：~20 行新增

### ATU-005：产品管理路由实现
- **文件**：`starter/routes_product.py`
- **变更**：
  - 导入 `get_current_user` from middleware, `Product` from models, `db` from app
  - 实现 `GET /products`（无需认证）
  - 实现 `POST /products`（含 RBAC 检查、输入验证）
- **预估行数**：~45 行

### ATU-006：订单系统路由实现 — 依赖 ATU-003, ATU-004
- **文件**：`starter/routes_order.py`
- **变更**：
  - 导入 `get_current_user, check_rate_limit, mark_order_placed` from middleware
  - 导入 `Order, Product` from models, `db` from app
  - 实现 `POST /orders`（含输入验证、限流、原子库存扣减、origin 参数）
  - 实现 `GET /orders`（含角色过滤）
- **预估行数**：~70 行

## 6. 错误处理规范

所有路由的错误响应统一格式：

| HTTP 状态码 | 使用场景 | 响应体 |
|-------------|----------|--------|
| 200/201 | 成功 | `{"status": "ok", "data": {...}}` |
| 400 | 请求参数错误（缺少字段、类型错误、quantity ≤ 0） | `{"status": "error", "message": "..."}` |
| 401 | 未认证（无 `X-User-Id` 或用户不存在） | `{"status": "error", "message": "..."}` |
| 403 | 权限不足（非 admin 创建产品） | `{"status": "error", "message": "..."}` |
| 404 | 资源不存在（产品不存在） | `{"status": "error", "message": "..."}` |
| 429 | 限流（10 秒内重复下单） | `{"status": "error", "message": "..."}` |
