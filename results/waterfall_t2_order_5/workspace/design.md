# T2-2 订单系统 — 方案设计文档

## 1. 数据库设计

数据库使用 SQLite（由 app.py 配置），通过 Flask-SQLAlchemy ORM 操作。表结构已在 models.py 中定义，此处仅描述使用方式。

### 1.1 模型关系图

```
Product ←──── OrderItem ────→ Order ←──── PaymentRequest
(FK: product_id)   (FK: order_id)    (FK: order_id)
```

### 1.2 关键查询设计

| 查询场景 | 实现方式 |
|---------|---------|
| 获取订单及其 items | `Order.query.get(id)` + `order.items`（lazy loading） |
| 按条件筛选订单 | `Order.query.filter_by(user_id=..., status=...)` |
| 幂等键查询 | `PaymentRequest.query.filter_by(order_id=..., idempotency_key=...).first()` |
| 库存查询 | `Product.query.get(id).stock` |

## 2. 模块划分

### 2.1 文件职责

| 文件 | 职责 | 行数估计 |
|------|------|---------|
| `routes_product.py` | 商品 CRUD（3 个端点） | ~40 行 |
| `routes_order.py` | 订单 CRUD + 状态机 + 支付（7 个端点） | ~150 行 |

### 2.2 模块间依赖

```
routes_product.py → from models import Product, db
routes_order.py   → from models import Product, Order, OrderItem, PaymentRequest, db
```

## 3. API 端点设计

### 3.1 商品端点（routes_product.py）

| 端点 | 方法 | 请求体/参数 | 成功码 | 响应 |
|------|------|------------|--------|------|
| `/products` | GET | — | 200 | `{"status": "ok", "data": [Product]}` |
| `/products` | POST | `{"name", "price", "stock"}` | 201 | `{"status": "ok", "data": Product}` |
| `/products/<id>` | GET | — | 200 | `{"status": "ok", "data": Product}` |

### 3.2 订单端点（routes_order.py）

| 端点 | 方法 | 请求体/参数/头 | 成功码 | 响应 |
|------|------|---------------|--------|------|
| `/orders` | GET | `?user_id=&status=` | 200 | `{"status": "ok", "data": [Order摘要]}`（不含 items） |
| `/orders` | POST | `{"user_id", "items"}` | 201 | `{"status": "ok", "data": {id, user_id, status, total_amount, created_at}}` |
| `/orders/<id>` | GET | — | 200 | `{"status": "ok", "data": {Order全量 + items: [OrderItem]}}` |
| `/orders/<id>/pay` | POST | Header: `Idempotency-Key` | 200 | `{"status": "ok", "data": {Order全量}}` |
| `/orders/<id>/ship` | POST | — | 200 | `{"status": "ok", "data": {Order全量}}` |
| `/orders/<id>/deliver` | POST | — | 200 | `{"status": "ok", "data": {Order全量}}` |
| `/orders/<id>/cancel` | POST | — | 200 | `{"status": "ok", "data": {Order全量}}` |

**注**：`GET /orders` 列表端点返回的 Order 摘要不包含 `items` 字段，避免 N+1 查询。仅 `GET /orders/<id>` 详情端点包含 `items`。

## 4. 关键算法设计

### 4.1 订单创建算法

```
function create_order(user_id, items):
    1. 验证 user_id 非空
    2. 验证 items 非空列表
    3. 对每个 item:
       a. 验证 quantity >= 1
       b. 查询 Product，不存在 → 400 {"status": "error", "message": "Product <id> not found"}
       c. 验证 product.stock >= quantity，不足 → 400 {"status": "error", "message": "Insufficient stock"}
    4. 计算 total_amount = Σ(product.price × quantity)
    5. 创建 Order 记录（status='pending'）
    6. 对每个 item 创建 OrderItem 记录（unit_price = product.price 快照）
    7. db.session.commit()
    8. 返回 201 + Order 对象（含 id, user_id, status, total_amount, created_at）
```

**设计决策**：创建订单时的库存检查是**软校验**（不预留库存），实际扣减发生在支付时。这意味着多个并发请求可能都通过库存检查成功创建订单，但支付时只有一个会成功（后续支付请求因状态已变为 paid 而返回 409）。对于当前 SQLite 单进程场景，这不是问题。

### 4.2 状态机转换

采用**白名单模式**实现状态转换校验：

```
VALID_TRANSITIONS = {
    'pending':  {'pay', 'cancel'},
    'paid':     {'ship', 'cancel'},
    'shipped':  {'deliver'},
    'delivered': set(),
    'cancelled': set(),
}
```

通用状态转换函数（**不包含 commit**，由调用方统一管理事务）：
```
def validate_transition(order, action):
    1. 查询 order，不存在 → 404
    2. 检查 action in VALID_TRANSITIONS[order.status]
       不在 → 409 Conflict
    3. 返回 True
```

**注意**：`validate_transition` 只做校验，不执行 commit。各状态转换端点自行管理整个事务（包括状态更新、时间戳设置、库存操作等），在所有操作完成后统一 `db.session.commit()`。

### 4.3 支付幂等性算法

```
function pay_order(order_id, idempotency_key):
    1. 查询 order，不存在 → 404
    2. order.status != 'pending' → 409
    3. 查询 PaymentRequest(order_id=order_id, idempotency_key=key):
       a. 已存在 → 幂等返回 200 + Order 对象（不执行任何副作用）
    4. 执行支付:
       a. 遍历 order.items，扣减对应 product.stock
       b. 创建 PaymentRequest(order_id, key, status='completed')
       c. order.status = 'paid'
       d. order.paid_at = datetime.utcnow()
    5. db.session.commit()（统一提交）
    6. 返回 200 + Order 对象
```

**注**：幂等键查询同时匹配 `order_id` 和 `idempotency_key`，确保不同订单间不会误匹配。

### 4.4 库存回滚算法（取消已付款订单）

```
function cancel_order(order_id):
    1. 查询 order，不存在 → 404
    2. 检查 'cancel' in VALID_TRANSITIONS[order.status]，不在 → 409
    3. 记录 original_status = order.status
    4. order.status = 'cancelled'
    5. order.cancelled_at = datetime.utcnow()
    6. 如果 original_status == 'paid':
       遍历 order.items:
           product = Product.query.get(item.product_id)
           product.stock += item.quantity
    7. db.session.commit()（统一提交，包含状态变更和库存回滚）
    8. 返回 200 + Order 对象
```

**关键修正**：整个取消操作在一个事务中完成，避免状态已 commit 但库存未回滚的数据不一致问题。

## 5. 实现计划

### ATU 执行顺序

```
ATU-003: 商品路由实现 (routes_product.py)
    ↓
ATU-004: 订单 CRUD 路由实现 (routes_order.py - 创建/查询/筛选)
    ↓
ATU-006: 支付幂等性实现 (routes_order.py - pay) [依赖 ATU-004]
    ↓
ATU-005: 订单状态机实现 (routes_order.py - ship/deliver/cancel) [依赖 ATU-004]
    ↓
ATU-007: 测试验证
    ↓
ATU-008: 最终交付
```

**注**：ATU-006（支付）先于 ATU-005（状态机）实现，因为支付会产生 `paid` 状态订单，而状态机的 `ship`/`cancel` 测试需要从 `paid` 状态出发。两者都修改同一文件，按顺序实现避免合并冲突。

### ATU-003 详细设计（商品路由）

**文件**: `starter/routes_product.py`
**Blueprint**: `product_bp`

```python
# GET /products — 列表
@product_bp.route('/products', methods=['GET'])
def list_products():
    products = Product.query.all()
    return jsonify({"status": "ok", "data": [serialize_product(p) for p in products]}), 200

# POST /products — 创建
@product_bp.route('/products', methods=['POST'])
def create_product():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON"}), 400
    # 校验 name, price, stock 必填
    if not data.get('name') or 'price' not in data or 'stock' not in data:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400
    product = Product(name=data['name'], price=float(data['price']), stock=int(data['stock']))
    db.session.add(product)
    db.session.commit()
    return jsonify({"status": "ok", "data": serialize_product(product)}), 201

# GET /products/<id> — 详情
@product_bp.route('/products/<int:id>', methods=['GET'])
def get_product(id):
    product = Product.query.get(id)
    if not product:
        return jsonify({"status": "error", "message": "Product not found"}), 404
    return jsonify({"status": "ok", "data": serialize_product(product)}), 200
```

### ATU-004 详细设计（订单 CRUD）

**文件**: `starter/routes_order.py`
**Blueprint**: `order_bp`

- `POST /orders`:
  1. 检查 `data = request.get_json()`，为 None → 400
  2. 验证 `user_id` 非空，`items` 非空列表
  3. 遍历 items 验证 product 存在、quantity >= 1、库存充足
  4. 创建 Order + OrderItem，计算 total_amount
  5. 返回 201 + `{id, user_id, status, total_amount, created_at}`
- `GET /orders/<id>`:
  1. 查询 Order，不存在 → 404
  2. 通过 `order.items` 获取 items 列表
  3. 返回 200 + Order 全量 + items
- `GET /orders`:
  1. 从 `request.args` 中提取 `user_id` 和 `status`（可选）
  2. 忽略其他非法查询参数
  3. 动态构建 `filter_by` 查询
  4. 返回 200 + Order 列表（不含 items，避免 N+1）

### ATU-006 详细设计（支付幂等性）

**文件**: `starter/routes_order.py`（追加到同一文件）

- `POST /orders/<id>/pay`:
  1. 检查 `Idempotency-Key` header，缺失 → 400
  2. 查询 order，不存在 → 404
  3. 检查 status=='pending'，否则 → 409
  4. 查询 `PaymentRequest.query.filter_by(order_id=order_id, idempotency_key=key).first()`
     - 存在 → 幂等返回 200 + serialize_order(order)
  5. 扣减库存 + 创建 PaymentRequest(status='completed') + 更新订单状态 → 统一 commit → 200

### ATU-005 详细设计（状态机）

**文件**: `starter/routes_order.py`（追加到同一文件）

- `POST /orders/<id>/ship`: 校验 status=='paid' → 更新为 'shipped' + 设置 shipped_at → 统一 commit → 200/409
- `POST /orders/<id>/deliver`: 校验 status=='shipped' → 更新为 'delivered' + 设置 delivered_at → 统一 commit → 200/409
- `POST /orders/<id>/cancel`: 校验 status in ['pending','paid'] → 如 paid 回滚库存 → 更新为 'cancelled' + 设置 cancelled_at → 统一 commit → 200/409

## 6. 序列化辅助函数

所有端点统一使用 `serialize_xxx()` 辅助函数将 ORM 对象转为字典：

```python
def serialize_product(p):
    return {"id": p.id, "name": p.name, "price": p.price, "stock": p.stock}

def serialize_order(o, include_items=False):
    data = {
        "id": o.id,
        "user_id": o.user_id,
        "status": o.status,
        "total_amount": o.total_amount,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        "shipped_at": o.shipped_at.isoformat() if o.shipped_at else None,
        "delivered_at": o.delivered_at.isoformat() if o.delivered_at else None,
        "cancelled_at": o.cancelled_at.isoformat() if o.cancelled_at else None,
    }
    if include_items:
        data["items"] = [serialize_order_item(i) for i in o.items]
    return data

def serialize_order_item(i):
    return {"id": i.id, "product_id": i.product_id, "quantity": i.quantity, "unit_price": i.unit_price}
```

**使用规则**：
- `GET /orders/<id>` 详情：调用 `serialize_order(order, include_items=True)`
- `GET /orders` 列表：调用 `serialize_order(order, include_items=False)`
- 状态转换端点：调用 `serialize_order(order, include_items=False)`

## 7. 错误处理策略

- **请求体无效**: 400 + `{"status": "error", "message": "Request body must be JSON"}`
- **输入验证失败**: 400 + `{"status": "error", "message": "Missing required fields"}` / `"Insufficient stock"` / `"Product <id> not found"`
- **资源不存在**: 404 + `{"status": "error", "message": "Order/Product not found"}`
- **状态冲突**: 409 + `{"status": "error", "message": "Invalid state transition"}`
- **缺少幂等键**: 400 + `{"status": "error", "message": "Idempotency-Key header is required"}`
- **服务端异常**: 500 + `{"status": "error", "message": str(e)}`（开发阶段）
