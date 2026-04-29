# 方案设计文档 (design.md)

## 1. 数据模型设计

### 1.1 User 模型（models.py）

已有定义，无需修改。

```python
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin' or 'user'
```

### 1.2 Product 模型（models.py）

已有定义，无需修改。

```python
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)
```

### 1.3 Order 模型（models.py）— 需变更

**变更内容**：新增 `origin` 字段。

```python
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    origin = db.Column(db.String(20), nullable=False, default='web')  # 新增
```

### 1.4 序列化辅助方法

为每个模型添加 `to_dict()` 方法，统一 API 响应格式：

- `User.to_dict()` → `{"id", "username", "role"}`
- `Product.to_dict()` → `{"id", "name", "price", "stock"}`
- `Order.to_dict()` → `{"id", "user_id", "product_id", "quantity", "total_price", "origin"}`

## 2. API 端点设计

### 2.1 产品管理路由（routes_product.py — Blueprint: `product_bp`）

#### GET /products

```
请求: GET /products
认证: 无需认证
响应 (200):
{
  "status": "ok",
  "data": [
    {"id": 1, "name": "Mouse", "price": 50.0, "stock": 5},
    ...
  ]
}
```

**实现逻辑**：
1. `Product.query.all()` 查询所有产品
2. 调用 `to_dict()` 序列化
3. 返回 `{"status": "ok", "data": [...]}`

#### POST /products

```
请求: POST /products
Header: X-User-Id: <user_id>
Body: {"name": str, "price": float, "stock": int}
认证: 需要 admin 角色
响应 (200/201):
{
  "status": "ok",
  "data": {"id": 1, "name": "Laptop", "price": 1000.0, "stock": 10}
}
错误:
  - 401: 无 X-User-Id header
  - 403: 非 admin 用户
  - 400: 参数缺失或无效
```

**实现逻辑**：
1. 调用 `get_current_user()` 获取用户 → None 则返回 401
2. 检查 `user.role == 'admin'` → 否则返回 403
3. 验证 `name` 参数存在且非空
4. 验证 `price` 参数存在且为正数（`price > 0`）
5. 验证 `stock` 参数存在且为非负整数（`stock >= 0`）
6. 创建 Product 对象并 `db.session.add()` + `db.session.commit()`
7. 返回 `{"status": "ok", "data": product.to_dict()}`

### 2.2 订单管理路由（routes_order.py — Blueprint: `order_bp`）

#### POST /orders

```
请求: POST /orders
Header: X-User-Id: <user_id>
Body: {"product_id": int, "quantity": int, "origin": str (可选)}
认证: 需要任意角色
限流: 同一用户 10 秒内只能成功 1 单
响应 (200/201):
{
  "status": "ok",
  "data": {
    "id": 1,
    "user_id": 1,
    "product_id": 1,
    "quantity": 2,
    "total_price": 100.0,
    "origin": "web"
  }
}
错误:
  - 401: 无 X-User-Id
  - 400: 参数缺失/无效/产品不存在/库存不足
  - 429: 超过限流频率
```

**实现逻辑**：
1. 调用 `get_current_user()` → None 则返回 401
2. 调用限流检查 `check_rate_limit(user.id)` → 超限返回 429
3. 验证 `product_id`, `quantity` 参数存在
4. **验证 `quantity` 为正整数（`quantity > 0`）**，否则返回 400（防止 quantity<=0 导致库存异常）
5. 查询 Product → 不存在返回 400/404
5. 检查 `product.stock >= quantity` → 不足返回 `{"status": "error", ...}`，HTTP 400
6. **原子性库存扣减**（见 3.2 节）
7. 创建 Order，`origin = request.json.get('origin', 'web')`
8. `total_price = product.price * quantity`
9. `db.session.add(order)` + `db.session.commit()`
10. 记录限流 `record_order_time(user.id)`（仅成功时记录）
11. 返回 `{"status": "ok", "data": order.to_dict()}`

#### GET /orders

```
请求: GET /orders
Header: X-User-Id: <user_id>
认证: 需要任意角色
响应 (200):
{
  "status": "ok",
  "data": [
    {"id": 1, "user_id": 1, "product_id": 1, "quantity": 2, "total_price": 100.0, "origin": "web"},
    ...
  ]
}
```

**实现逻辑**：
1. 调用 `get_current_user()` → None 则返回 401
2. 如果 `user.role == 'admin'` → `Order.query.all()`
3. 否则 → `Order.query.filter_by(user_id=user.id).all()`
4. 返回 `{"status": "ok", "data": [o.to_dict() for o in orders]}`

## 3. 中间件设计（middleware.py）

### 3.1 认证函数（已有）

`get_current_user()` 已实现，从 `X-User-Id` header 获取 User 对象。

**异常处理增强**：当前实现中 `int(user_id)` 在 `X-User-Id` 为非数字字符串时会抛出 `ValueError`，导致 500 错误。需增加 try/except 包裹，捕获 `ValueError` 后返回 `None`（即视为未认证，返回 401）。

### 3.2 限流功能（新增）

**设计方案**：基于内存字典的滑动窗口限流。

```python
import time

# 存储格式: {user_id: last_success_timestamp}
_order_timestamps = {}

def check_rate_limit(user_id: int) -> bool:
    """
    检查用户是否超过下单频率限制。
    返回 True 表示允许下单，False 表示超限。
    """
    now = time.time()
    last_time = _order_timestamps.get(user_id, 0)
    return (now - last_time) >= 10  # 10 秒窗口

def record_order_time(user_id: int) -> None:
    """记录成功下单时间（仅在订单创建成功后调用）。"""
    _order_timestamps[user_id] = time.time()
```

**关键设计决策**：
- 使用简单的固定窗口限流（10 秒窗口），而非滑动窗口。对于测试场景足够。
- **仅在订单成功创建后**调用 `record_order_time()`，失败的订单不计入限流。
- 使用内存字典存储，无需外部依赖（Redis 等），适合单进程场景。

### 3.3 导出接口

middleware.py 导出以下函数：
- `get_current_user()` — 认证
- `check_rate_limit(user_id)` — 限流检查
- `record_order_time(user_id)` — 记录下单时间

## 4. 库存扣减原子性设计

### 4.1 方案：SELECT FOR UPDATE 行级锁

使用 SQLAlchemy 的 `with_for_update()` 对产品行加排他锁，确保并发安全。

```python
product = Product.query.filter_by(id=product_id).with_for_update().first()
if product is None:
    return error_response(400/404)
if product.stock < quantity:
    return error_response({"status": "error", ...})
product.stock -= quantity
order = Order(user_id=user.id, product_id=product_id,
              quantity=quantity, total_price=product.price * quantity,
              origin=request.json.get('origin', 'web'))
db.session.add(order)
db.session.commit()  # 锁在 commit 后释放
```

**原子性保证**：
1. `with_for_update()` 对 Product 行加排他锁
2. 其他并发请求在锁释放前阻塞
3. 读取 stock → 检查 → 扣减 → 创建订单 → commit 为原子操作
4. 不会出现负数库存

**⚠️ SQLite 局限性说明**：
本系统使用 SQLite 数据库。SQLite 使用数据库级文件锁，**不支持真正的行级锁**。`SELECT ... FOR UPDATE` 在 SQLite 上被语法接受但实际是 no-op。当前安全性依赖于 SQLite 固有的 SERIALIZABLE 隔离级别（写操作串行化）和测试场景的顺序执行特性。`with_for_update()` 不会报错，且如果将来迁移到 PostgreSQL/MySQL 则自动获得真正的行级锁。

## 5. 错误处理统一规范

所有路由统一使用以下错误响应格式：

```python
def error_response(message, status_code):
    return jsonify({"status": "error", "message": message}), status_code
```

| 场景 | HTTP 状态码 | message |
|------|------------|---------|
| 缺少 X-User-Id | 401 | "Authentication required" |
| 权限不足 | 403 | "Forbidden" |
| 参数缺失/无效 | 400 | 具体描述 |
| 产品不存在 | 404 | "Product not found" |
| 库存不足 | 400 | "Insufficient stock" |
| 超过限流 | 429 | "Too many requests" |
| quantity 非正整数 | 400 | "Quantity must be a positive integer" |

## 6. 模块依赖关系

```
app.py (不可修改)
  ├── models.py
  │     └── from app import db
  ├── middleware.py
  │     └── from models import User
  ├── routes_product.py
  │     └── from middleware import get_current_user
  │     └── from models import Product
  └── routes_order.py
        └── from middleware import get_current_user, check_rate_limit, record_order_time
        └── from models import Product, Order
```

## 7. 实现计划（ATU 执行顺序）

| 顺序 | ATU | 文件 | 依赖 | 描述 |
|------|-----|------|------|------|
| 1 | ATU-003 | models.py | design.md | Order 新增 origin 字段 + to_dict() |
| 2 | ATU-004 | middleware.py | design.md | 新增限流函数 check_rate_limit + record_order_time |
| 3 | ATU-005 | routes_product.py | ATU-003, ATU-004 | 实现 GET/POST /products |
| 4 | ATU-006 | routes_order.py | ATU-003, ATU-004 | 实现 GET/POST /orders（含 origin、限流、原子库存） |

## 8. 需求审查警告处理

来自 Reviewer 的警告：`test_basic.py` 中 `test_no_user_id_returns_error` 的断言范围（400/401/403）比 requirements.md 的要求（401）更宽松。设计文档按 requirements.md 严格要求实现（返回 401），测试断言范围过宽不影响实现正确性。
