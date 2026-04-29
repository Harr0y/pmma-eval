# 方案设计文档 — T3 微型电商订单系统

## 1. 数据库设计

### 1.1 User 模型（无需修改）
```python
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin' or 'user'
```

### 1.2 Product 模型（无需修改）
```python
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)
```

### 1.3 Order 模型（需修改 — ATU-003）
新增 `origin` 字段：
```python
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    origin = db.Column(db.String(20), nullable=False, default='web')  # NEW
```

新增 `to_dict()` 序列化方法，统一返回所有字段（含 origin）。

## 2. API 端点设计

### 2.1 产品路由（routes_product.py — ATU-005）

#### GET /products
```
无权限要求
Response 200:
{
  "status": "ok",
  "data": [
    {"id": 1, "name": "Mouse", "price": 50.0, "stock": 5},
    ...
  ]
}
```

#### POST /products
```
权限: Admin only
Request: {"name": str, "price": float, "stock": int}
Response 201:
{
  "status": "ok",
  "data": {"id": 1, "name": "Laptop", "price": 1000.0, "stock": 10}
}

Error Responses:
- 401: 无 X-User-Id header 或用户不存在
- 403: 非管理员
- 400: 缺少必要字段或字段类型错误
```

### 2.2 订单路由（routes_order.py — ATU-006）

#### POST /orders
```
权限: 需登录
Request: {"product_id": int, "quantity": int, "origin": str (optional)}
Response 201:
{
  "status": "ok",
  "data": {
    "id": 1,
    "user_id": 2,
    "product_id": 1,
    "quantity": 2,
    "total_price": 100.0,
    "origin": "web"
  }
}

Error Responses:
- 401: 无 X-User-Id header 或用户不存在
- 400: 缺少字段、产品不存在、quantity <= 0
- {"status": "error", "message": "..."}: 库存不足
- 429: 限流（10 秒内重复下单）
```

#### GET /orders
```
权限: 需登录
Admin → 返回所有订单
User  → 返回 user_id 匹配的订单

Response 200:
{
  "status": "ok",
  "data": [
    {"id": 1, "user_id": 2, "product_id": 1, "quantity": 2, "total_price": 100.0, "origin": "web"},
    ...
  ]
}

Error Responses:
- 401: 无 X-User-Id header 或用户不存在
```

## 3. 限流策略设计（middleware.py — ATU-004）

### 3.1 方案：内存字典 + 时间戳

```python
# middleware.py
_order_timestamps = {}  # {user_id: last_order_timestamp}

def check_rate_limit(user_id, window=10):
    """
    检查用户是否在限流窗口内。
    Args:
        user_id: 用户 ID
        window: 限流窗口（秒），默认 10 秒
    Returns:
        (allowed: bool, remaining_seconds: int)
    """
    import time
    now = time.time()
    last_time = _order_timestamps.get(user_id)
    if last_time is not None and (now - last_time) < window:
        return False, int(window - (now - last_time))
    return True, 0

def record_order(user_id):
    """记录用户下单时间"""
    import time
    _order_timestamps[user_id] = time.time()
```

**设计要点：**
- 使用进程内字典存储，无需外部依赖
- 10 秒窗口：从成功下单时刻起算
- 返回 tuple (allowed, remaining_seconds) 供路由层判断
- 路由层在成功下单后调用 `record_order(user_id)` 记录

## 4. 原子库存扣减策略（routes_order.py — ATU-006）

### 4.1 方案：SQLAlchemy 条件更新（乐观锁）

```python
# 原子扣减库存
result = db.session.execute(
    db.update(Product)
    .where(Product.id == product_id, Product.stock >= quantity)
    .values(stock=Product.stock - quantity)
)
rows_affected = result.rowcount
if rows_affected == 0:
    # 库存不足或产品不存在
    db.session.rollback()
    return error_response(...)
db.session.commit()
```

**设计要点：**
- 使用 `WHERE stock >= quantity` 条件确保不会超卖
- `rowcount == 0` 同时覆盖产品不存在和库存不足两种情况
- SQLAlchemy 的 `db.update()` 生成单条 SQL，数据库级别原子性
- 不需要显式加锁（`with_for_update()`），减少死锁风险

## 5. 实现计划（ATU 执行顺序）

```
ATU-003 (models.py) ──────┐
                          ├──→ ATU-006 (routes_order.py) ──→ ATU-007 (testing)
ATU-004 (middleware.py) ──┘
ATU-005 (routes_product.py) ───────────────────────────────→ ATU-007 (testing)
```

**执行顺序：**
1. **ATU-003** — models.py（修改 Order 模型）
2. **ATU-004** — middleware.py（新增限流功能）
3. **ATU-005** — routes_product.py（产品路由，可与 ATU-003/004 并行，但按瀑布顺序执行）
4. **ATU-006** — routes_order.py（依赖 ATU-003 和 ATU-004）

## 6. 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 限流存储 | 进程内字典 | 单进程部署，无需 Redis 等外部依赖 |
| 库存原子性 | SQL 条件更新 | 单条 SQL 原子操作，无死锁风险 |
| 序列化 | 模型 to_dict() 方法 | 统一序列化逻辑，确保 origin 字段始终包含 |
| 错误格式 | `{"status": "error", "message": "..."}` | 与测试断言一致（测试检查 `status == 'error'`） |
| 限流触发时机 | 成功下单后记录 | 符合"只能成功提交 1 笔"的语义 |
