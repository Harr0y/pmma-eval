# 方案设计文档 — T3 微型电商订单系统

## 1. 架构概览

```
app.py (不可修改)
  ├── models.py          — 数据模型层
  ├── middleware.py       — 认证 + 限流中间件
  ├── routes_product.py  — 产品管理 Blueprint (product_bp)
  └── routes_order.py    — 订单管理 Blueprint (order_bp)
```

模块依赖关系：
- `routes_product.py` → imports `models.Product`, `middleware.get_current_user`
- `routes_order.py` → imports `models.Product`, `models.Order`, `middleware.get_current_user`, `middleware.check_rate_limit`
- `middleware.py` → imports `models.User`

## 2. 数据库表设计

### 2.1 User 表（无需修改）

```python
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin' or 'user'
```

### 2.2 Product 表（无需修改）

```python
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)
```

### 2.3 Order 表（需要新增 origin 字段）

```python
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    origin = db.Column(db.String(50), nullable=False, default='web')  # 新增
```

**变更说明**：新增 `origin` 字段，String(50)，NOT NULL，默认值 `'web'`。对应 FR-004。

## 3. API 端点设计

### 3.1 GET /products（产品列表）

**文件**：`routes_product.py`
**认证**：不需要
**逻辑**：查询所有 Product，序列化为列表返回

```python
@product_bp.route('/products', methods=['GET'])
def list_products():
    products = Product.query.all()
    data = [{
        'id': p.id,
        'name': p.name,
        'price': p.price,
        'stock': p.stock
    } for p in products]
    return jsonify({'status': 'ok', 'data': data})
```

### 3.2 POST /products（创建产品）

**文件**：`routes_product.py`
**认证**：需要（X-User-Id）
**权限**：仅 admin
**逻辑**：
1. 调用 `get_current_user()` 获取用户
2. 用户不存在 → 401
3. 用户非 admin → 403
4. 验证请求体（name, price, stock）
5. 创建 Product 并返回

```python
@product_bp.route('/products', methods=['POST'])
def create_product():
    user = get_current_user()
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    if user.role != 'admin':
        return jsonify({'status': 'error', 'message': 'Forbidden'}), 403
    data = request.get_json()
    # 验证 + 创建 Product
    ...
    return jsonify({'status': 'ok', 'data': {...}}), 201
```

### 3.3 POST /orders（创建订单）

**文件**：`routes_order.py`
**认证**：需要（X-User-Id）
**限流**：调用 `check_rate_limit(user_id)`
**逻辑**：
1. 调用 `get_current_user()` 获取用户
2. 用户不存在 → 401
3. 调用 `check_rate_limit(user.id)` 检查限流 → 429
4. 解析请求体（product_id, quantity, origin 可选）
5. 验证 product_id 存在 → 400/404
6. 验证库存充足（使用原子操作）
7. 创建 Order，扣减库存
8. 记录限流时间戳

```python
@order_bp.route('/orders', methods=['POST'])
def create_order():
    user = get_current_user()
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    if not check_rate_limit(user.id):
        return jsonify({'status': 'error', 'message': 'Rate limit exceeded'}), 429
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = data.get('quantity')
    origin = data.get('origin', 'web')
    # 原子库存扣减
    ...
    return jsonify({'status': 'ok', 'data': {...}}), 201
```

### 3.4 GET /orders（订单列表）

**文件**：`routes_order.py`
**认证**：需要（X-User-Id）
**权限**：Admin 看全部，普通用户看自己的
**逻辑**：
1. 调用 `get_current_user()` 获取用户
2. 用户不存在 → 401
3. Admin → 查询所有 Order
4. 普通用户 → 查询 `user_id == current_user.id` 的 Order
5. 序列化返回（包含 origin 字段）

```python
@order_bp.route('/orders', methods=['GET'])
def list_orders():
    user = get_current_user()
    if not user:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    if user.role == 'admin':
        orders = Order.query.all()
    else:
        orders = Order.query.filter_by(user_id=user.id).all()
    data = [{
        'id': o.id,
        'user_id': o.user_id,
        'product_id': o.product_id,
        'quantity': o.quantity,
        'total_price': o.total_price,
        'origin': o.origin
    } for o in orders]
    return jsonify({'status': 'ok', 'data': data})
```

## 4. 关键算法逻辑

### 4.1 库存扣减原子性保证（FR-006）

**方案**：使用 SQLAlchemy 的 `with_for_update()` 行级锁 + 条件更新。

```python
# 伪代码
product = Product.query.filter_by(id=product_id).with_for_update().first()
if not product:
    return error(404)
if product.stock < quantity:
    return error, stock unchanged
product.stock -= quantity
db.session.add(order)
db.session.commit()
```

**关键点**：
- `with_for_update()` 在 SELECT 时加行级排他锁，防止并发读取相同库存值
- 整个检查-扣减-创建操作在一个事务中完成
- 如果库存不足，不修改任何数据，直接返回错误
- SQLite 支持 `FOR UPDATE` 语义（虽然单写场景下本身串行化，但代码层面仍使用此模式保证正确性）

**测试用例覆盖**：
- `test_stock_no_negative`：库存为 1 时两笔订单，第二笔失败
- `test_zero_stock_order_fails`：库存为 0 时不能下单
- `test_insufficient_stock`：库存不足时下单失败，库存不变

### 4.2 用户下单限流（FR-005）

**方案**：内存字典记录每个 user_id 的最后一次成功下单时间。

```python
# middleware.py
_rate_limit_store = {}  # {user_id: last_success_timestamp}

def check_rate_limit(user_id):
    """检查用户是否被限流。返回 True 表示允许，False 表示被限流。"""
    import time
    now = time.time()
    last_time = _rate_limit_store.get(user_id, 0)
    if now - last_time < 10:
        return False
    return True

def record_order_success(user_id):
    """记录成功下单时间。"""
    import time
    _rate_limit_store[user_id] = time.time()
```

**关键点**：
- 限流基于**成功**下单（FR-005-1），而非请求次数
- 10 秒窗口期
- `check_rate_limit()` 在下单前调用
- `record_order_success()` 在订单创建成功后调用
- 不同 user_id 之间完全隔离（FR-005-3）

**注意**：内存字典方案适用于单进程场景。对于 PM2 多进程部署，后续可考虑 Redis。当前阶段 SQLite + 单进程场景下内存方案足够。

### 4.3 序列化辅助函数

```python
def product_to_dict(p):
    return {
        'id': p.id,
        'name': p.name,
        'price': p.price,
        'stock': p.stock
    }

def order_to_dict(o):
    return {
        'id': o.id,
        'user_id': o.user_id,
        'product_id': o.product_id,
        'quantity': o.quantity,
        'total_price': o.total_price,
        'origin': o.origin
    }
```

## 5. 模块间接口契约

### 5.1 models.py 导出

```python
from models import User, Product, Order
# User: id, username, role
# Product: id, name, price, stock
# Order: id, user_id, product_id, quantity, total_price, origin
```

### 5.2 middleware.py 导出

```python
from middleware import get_current_user, check_rate_limit, record_order_success
# get_current_user() -> User | None
# check_rate_limit(user_id: int) -> bool
# record_order_success(user_id: int) -> None
```

### 5.3 routes_product.py 导出

```python
from routes_product import product_bp  # Blueprint named 'product_bp'
```

### 5.4 routes_order.py 导出

```python
from routes_order import order_bp  # Blueprint named 'order_bp'
```

## 6. 错误处理策略

| 场景 | HTTP 状态码 | 响应格式 |
|------|------------|----------|
| 缺少 X-User-Id / 用户不存在 | 401 | `{"status": "error", "message": "Unauthorized"}` |
| 非 admin 创建产品 | 403 | `{"status": "error", "message": "Forbidden"}` |
| product_id 不存在 | 404 | `{"status": "error", "message": "Product not found"}` |
| 参数无效/缺失 | 400 | `{"status": "error", "message": "Invalid request"}` |
| 库存不足 | 400 | `{"status": "error", "message": "Insufficient stock"}` |
| 触发限流 | 429 | `{"status": "error", "message": "Rate limit exceeded"}` |

**统一约定**：
- 所有成功响应：`{"status": "ok", "data": {...}}`
- 所有错误响应：`{"status": "error", "message": "..."}`

## 7. 实现计划（ATU 执行顺序）

```
ATU-003 (models.py) ─┐
                      ├──→ ATU-005 (routes_product.py) ─┐
ATU-004 (middleware.py)┤                                 ├──→ ATU-007 (测试验证) → ATU-008 (交付)
                      ├──→ ATU-006 (routes_order.py) ──┘
```

执行顺序：
1. **ATU-003**：models.py — 新增 Order.origin 字段
2. **ATU-004**：middleware.py — 保留现有 get_current_user()，新增 check_rate_limit() 和 record_order_success()
3. **ATU-005**：routes_product.py — 实现 GET/POST /products
4. **ATU-006**：routes_order.py — 实现 POST/GET /orders（含原子库存、origin、限流）
5. **ATU-007**：运行全部测试
6. **ATU-008**：最终交付

ATU-003 和 ATU-004 无相互依赖，可顺序执行。ATU-005 和 ATU-006 依赖前两者，需等待完成。

## 8. 测试用例映射

| ATU | 覆盖的测试用例 |
|-----|---------------|
| ATU-003 + ATU-005 | test_basic.py: TestProductManagement (4 tests), TestRBAC (2 tests) |
| ATU-003 + ATU-006 | test_basic.py: TestOrderSystem (7 tests) |
| ATU-003 + ATU-004 + ATU-006 | test_change.py: TestOrderOrigin (2 tests), TestRateLimiting (2 tests), TestAtomicStock (2 tests) |
