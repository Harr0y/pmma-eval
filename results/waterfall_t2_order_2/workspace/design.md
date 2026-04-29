# T2-2 订单系统 — 方案设计文档

## 1. 系统架构

### 1.1 模块结构

```
starter/
  app.py              # Flask app 工厂 + DB 初始化（不可修改）
  models.py           # 数据模型（Product, Order, OrderItem, PaymentRequest）— 已定义，不可修改
  routes_product.py   # 商品管理 Blueprint（product_bp）— 需实现
  routes_order.py     # 订单管理 Blueprint（order_bp）— 需实现
```

### 1.2 模块依赖关系

```
app.py
  ├── imports models.py (Product, Order, OrderItem, PaymentRequest)
  ├── imports routes_product.py (product_bp)
  └── imports routes_order.py (order_bp)

routes_product.py
  ├── imports flask (Blueprint, request, jsonify)
  └── imports models.py (Product, db)

routes_order.py
  ├── imports flask (Blueprint, request, jsonify)
  ├── imports models.py (Product, Order, OrderItem, PaymentRequest, db)
  └── imports datetime
```

## 2. API 端点设计

### 2.1 商品路由（routes_product.py — product_bp）

#### POST /products
```python
@product_bp.route('/products', methods=['POST'])
```
- **输入**: JSON body `{"name": str, "price": float, "stock": int}`
- **校验**: name、price、stock 必须存在，否则返回 400
- **处理**: 创建 Product 记录，db.session.add() + db.session.commit()
- **输出**: 201 `{"status": "ok", "data": product_to_dict(product)}`
- **序列化**: `{"id": int, "name": str, "price": float, "stock": int}`

#### GET /products
```python
@product_bp.route('/products', methods=['GET'])
```
- **处理**: `Product.query.all()`
- **输出**: 200 `{"status": "ok", "data": [product_to_dict(p) for p in products]}`

#### GET /products/<int:id>
```python
@product_bp.route('/products/<int:id>', methods=['GET'])
```
- **处理**: `Product.query.get_or_404(id)`
- **输出**: 200 `{"status": "ok", "data": product_to_dict(product)}`
- **错误**: 404（Flask-SQLAlchemy get_or_404 自动处理）

### 2.2 订单路由（routes_order.py — order_bp）

#### POST /orders
```python
@order_bp.route('/orders', methods=['POST'])
```
- **输入**: JSON body `{"user_id": str, "items": [{"product_id": int, "quantity": int}, ...]}`
- **校验**:
  1. `user_id` 必须存在，`items` 必须为非空列表 → 400
  2. 遍历 items，校验每个 product_id 对应的 Product 存在 → 400
  3. 校验每个商品的库存 >= quantity → 400
- **处理**:
  1. 计算 `total_amount = sum(product.price * item.quantity)`
  2. 创建 Order 记录（status='pending', total_amount=计算值）
  3. 遍历 items，创建 OrderItem 记录（unit_price = product.price）
  4. db.session.commit()
- **输出**: 201 `{"status": "ok", "data": order_to_dict(order)}`

#### GET /orders/<int:id>
```python
@order_bp.route('/orders/<int:id>', methods=['GET'])
```
- **处理**: `Order.query.get_or_404(id)`，包含 items 列表
- **输出**: 200 `{"status": "ok", "data": order_to_dict_with_items(order)}`

#### GET /orders
```python
@order_bp.route('/orders', methods=['GET'])
```
- **查询参数**: `user_id`（可选）, `status`（可选）
- **处理**:
  - `query = Order.query`
  - 如果有 `user_id` 参数：`query = query.filter_by(user_id=user_id)`
  - 如果有 `status` 参数：`query = query.filter_by(status=status)`
  - `orders = query.all()`
- **输出**: 200 `{"status": "ok", "data": [order_to_dict(o) for o in orders]}`

#### POST /orders/<int:id>/pay
```python
@order_bp.route('/orders/<int:id>/pay', methods=['POST'])
```
- **Header**: `Idempotency-Key`（必须）
- **校验**:
  1. 缺少 Idempotency-Key header → 400
  2. Order 存在 → 404
  3. Order status == 'pending' → 409
- **幂等处理**:
  1. 查询 `PaymentRequest.query.filter_by(idempotency_key=key, order_id=order.id).first()`
  2. 如果已存在 → 直接返回当前订单状态（不重复扣库存）
  3. 如果不存在 → 创建 PaymentRequest，扣减库存，更新订单
- **库存扣减**:
  - 遍历 order.items，对每个 item：`product.stock -= item.quantity`
- **状态更新**:
  - `order.status = 'paid'`
  - `order.paid_at = datetime.utcnow()`
- **输出**: 200 `{"status": "ok", "data": order_to_dict(order)}`

#### POST /orders/<int:id>/ship
```python
@order_bp.route('/orders/<int:id>/ship', methods=['POST'])
```
- **校验**: Order status == 'paid' → 409
- **处理**: `order.status = 'shipped'`, `order.shipped_at = datetime.utcnow()`
- **输出**: 200 `{"status": "ok", "data": order_to_dict(order)}`

#### POST /orders/<int:id>/deliver
```python
@order_bp.route('/orders/<int:id>/deliver', methods=['POST'])
```
- **校验**: Order status == 'shipped' → 409
- **处理**: `order.status = 'delivered'`, `order.delivered_at = datetime.utcnow()`
- **输出**: 200 `{"status": "ok", "data": order_to_dict(order)}`

#### POST /orders/<int:id>/cancel
```python
@order_bp.route('/orders/<int:id>/cancel', methods=['POST'])
```
- **校验**: Order status in ('pending', 'paid') → 409
- **库存回滚**（仅 paid 状态）:
  - 遍历 order.items，对每个 item：`product.stock += item.quantity`
- **处理**: `order.status = 'cancelled'`, `order.cancelled_at = datetime.utcnow()`
- **输出**: 200 `{"status": "ok", "data": order_to_dict(order)}`

## 3. 状态机设计

### 3.1 合法状态转换表

| 当前状态 | 操作 | 目标状态 | 附带动作 |
|----------|------|----------|----------|
| pending | pay | paid | 扣减库存，记录 PaymentRequest，设置 paid_at |
| paid | ship | shipped | 设置 shipped_at |
| shipped | deliver | delivered | 设置 delivered_at |
| pending | cancel | cancelled | 设置 cancelled_at（无库存操作） |
| paid | cancel | cancelled | 回滚库存，设置 cancelled_at |

### 3.2 非法状态转换（返回 409）

| 当前状态 | 操作 | 原因 |
|----------|------|------|
| pending | ship | 未支付不可发货 |
| pending | deliver | 未发货不可送达 |
| paid | deliver | 未发货不可送达 |
| shipped | pay | 已支付 |
| shipped | cancel | 已发货不可取消 |
| delivered | pay/ship/deliver/cancel | 终态不可变更 |
| cancelled | pay/ship/deliver/cancel | 终态不可变更 |

### 3.3 状态转换实现方式

使用辅助函数 `check_and_transition(order, expected_status, new_status)`：
```python
def check_and_transition(order, expected_status, new_status):
    if order.status != expected_status:
        return False
    order.status = new_status
    return True
```

对于 cancel 操作（允许多个源状态）：
```python
def can_cancel(order):
    return order.status in ('pending', 'paid')
```

## 4. 幂等性设计

### 4.1 机制

利用 PaymentRequest 表的 `idempotency_key` UNIQUE 约束保证幂等：

```
请求到达 → 提取 Idempotency-Key header
  ├── 缺失 → 400 Bad Request
  ├── 查询 PaymentRequest(order_id, key)
  │   ├── 已存在 → 返回当前订单状态（幂等）
  │   └── 不存在 → 正常处理支付流程
```

### 4.2 幂等处理的详细逻辑

```python
def pay_order(order_id, idempotency_key):
    order = Order.query.get_or_404(order_id)
    if order.status != 'pending':
        return error_response(409, ...)

    # 幂等检查
    existing = PaymentRequest.query.filter_by(
        order_id=order_id,
        idempotency_key=idempotency_key
    ).first()
    if existing:
        # 已处理过，直接返回当前状态
        return ok_response(order)

    # 首次处理
    payment = PaymentRequest(
        order_id=order_id,
        idempotency_key=idempotency_key,
        status='completed'
    )
    db.session.add(payment)

    # 扣减库存
    for item in order.items:
        product = Product.query.get(item.product_id)
        product.stock -= item.quantity

    order.status = 'paid'
    order.paid_at = datetime.utcnow()
    db.session.commit()
    return ok_response(order)
```

### 4.3 边界情况

- **重复 key + 已支付订单**: 查到 PaymentRequest → 返回当前 paid 状态（不重复扣库存）
- **新 key + 已支付订单**: status != 'pending' → 409 Conflict
- **缺少 key**: 400 Bad Request

## 5. 序列化函数设计

### 5.1 product_to_dict(product)
```python
def product_to_dict(product):
    return {
        'id': product.id,
        'name': product.name,
        'price': product.price,
        'stock': product.stock
    }
```

### 5.2 order_to_dict(order)
```python
def order_to_dict(order):
    return {
        'id': order.id,
        'user_id': order.user_id,
        'status': order.status,
        'total_amount': order.total_amount,
        'created_at': order.created_at.isoformat() if order.created_at else None
    }
```

### 5.3 order_to_dict_with_items(order)
```python
def order_to_dict_with_items(order):
    data = order_to_dict(order)
    data['items'] = [{
        'id': item.id,
        'product_id': item.product_id,
        'quantity': item.quantity,
        'unit_price': item.unit_price
    } for item in order.items]
    return data
```

## 6. 错误处理策略

### 6.1 统一错误响应格式
```python
def error_response(status_code, message):
    return jsonify({"status": "error", "message": message}), status_code

def ok_response(data, status_code=200):
    return jsonify({"status": "ok", "data": data}), status_code
```

### 6.2 HTTP 状态码使用规范

| 场景 | 状态码 | 说明 |
|------|--------|------|
| 创建成功 | 201 | POST 创建资源 |
| 查询成功 | 200 | GET 请求 |
| 状态变更成功 | 200 | POST 状态变更 |
| 缺少必要字段 | 400 | 请求参数不合法 |
| 资源不存在 | 404 | Order/Product 不存在 |
| 状态冲突 | 409 | 非法状态跳转 |
| 缺少幂等键 | 400 | 支付时无 Idempotency-Key |

### 6.3 输入校验清单

| 端点 | 校验项 |
|------|--------|
| POST /products | name、price、stock 必须存在 |
| POST /orders | user_id 必须存在；items 必须为非空列表；product_id 必须存在且库存充足 |
| POST /orders/.../pay | Idempotency-Key header 必须存在 |

## 7. 实现计划（ATU 拆分与执行顺序）

### ATU-003: 实现商品路由 routes_product.py
- **文件**: `starter/routes_product.py`
- **内容**:
  - `product_to_dict()` 序列化函数
  - `POST /products` — 创建商品
  - `GET /products` — 列出商品
  - `GET /products/<int:id>` — 获取商品详情
- **预估行数**: ~30 行
- **复杂度**: S

### ATU-004: 实现订单路由 — 创建订单与查询
- **文件**: `starter/routes_order.py`
- **内容**:
  - `order_to_dict()` 和 `order_to_dict_with_items()` 序列化函数
  - `error_response()` 和 `ok_response()` 辅助函数
  - `POST /orders` — 创建订单（含库存校验、金额计算、OrderItem 创建）
  - `GET /orders/<int:id>` — 获取订单详情（含 items）
  - `GET /orders` — 筛选订单（支持 user_id、status 参数）
- **预估行数**: ~60 行
- **复杂度**: M

### ATU-005: 实现订单路由 — 状态机与付款
- **文件**: `starter/routes_order.py`（追加到 ATU-004 的代码之后）
- **内容**:
  - `POST /orders/<int:id>/pay` — 幂等付款 + 库存扣减
  - `POST /orders/<int:id>/ship` — 发货
  - `POST /orders/<int:id>/deliver` — 送达
  - `POST /orders/<int:id>/cancel` — 取消（含 paid 状态库存回滚）
  - 非法状态跳转返回 409
- **预估行数**: ~80 行
- **复杂度**: L

## 8. Reviewer 警告规避

Reviewer 在需求审查阶段提出了以下非阻塞性建议，本设计已做如下处理：

| 建议项 | 处理方式 |
|--------|----------|
| items 为空数组时的行为 | POST /orders 校验 items 必须为非空列表 |
| 重复 product_id | 不做限制，允许同一商品出现在多个 item 中（每个 item 独立扣减库存） |
| cancelled 状态再次取消 | 状态机设计中 cancelled 为终态，任何操作均返回 409 |
| 无查询参数返回全部订单 | GET /orders 不传参数时返回全部订单 |
