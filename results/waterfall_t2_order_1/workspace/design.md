# T2-2 方案设计文档

## 1. 数据库表设计

### 1.1 表结构（已由 models.py 定义，无需修改）

数据库使用 SQLite，通过 Flask-SQLAlchemy ORM 管理。models.py 已完整定义了四个模型：

- **Product**：商品表，含 id/name/price/stock
- **Order**：订单表，含 id/user_id/status/total_amount/五个时间戳字段
- **OrderItem**：订单项表，含 id/order_id(FK)/product_id(FK)/quantity/unit_price
- **PaymentRequest**：支付请求表，含 id/order_id(FK)/idempotency_key(UNIQUE)/status/created_at

**设计决策**：models.py 已经完整实现，开发阶段不需要修改此文件。

## 2. API 端点设计

### 2.1 商品路由（routes_product.py）— ATU-003

#### GET /products
```python
@product_bp.route('/products', methods=['GET'])
def list_products():
    # 查询所有 Product 记录
    # 序列化为 [{"id": int, "name": str, "price": float, "stock": int}, ...]
    # 无商品时返回 {"status": "ok", "data": []}
    # 返回 200 + {"status": "ok", "data": [...]}
```

#### POST /products
```python
@product_bp.route('/products', methods=['POST'])
def create_product():
    # 1. 防御性检查：request.json is None → 400 "Request body must be JSON"
    # 2. 从 request.json 获取 name, price, stock
    # 3. 校验：三个字段都存在且非 None，否则返回 400
    # 4. 创建 Product 记录，db.session.commit()
    # 5. 返回 201 + {"status": "ok", "data": {...}}
```

#### GET /products/<id>
```python
@product_bp.route('/products/<int:id>', methods=['GET'])
def get_product(id):
    # 查询 Product by id
    # 不存在返回 404
    # 返回 200 + {"status": "ok", "data": {...}}
```

### 2.2 订单路由（routes_order.py）— ATU-004

#### POST /orders — 创建订单
```python
@order_bp.route('/orders', methods=['POST'])
def create_order():
    # 1. 防御性检查：request.json is None → 400 "Request body must be JSON"
    # 2. 从 request.json 获取 user_id, items
    # 3. 校验 user_id 存在且非空字符串
    # 4. 校验 items 存在且为非空列表（len(items) > 0）
    # 5. 遍历 items：
    #    - 校验 product_id 对应的 Product 存在（不存在返回 400）
    #    - 校验 product.stock >= quantity（不足返回 400）
    # 6. 计算 total_amount = sum(product.price * quantity)
    # 7. 创建 Order 记录（status='pending'）
    # 8. 创建 OrderItem 记录（unit_price = product.price 快照）
    # 9. 返回 201 + {"status": "ok", "data": {"id", "user_id", "status", "total_amount", "created_at"}}
```

#### GET /orders/<id> — 订单详情
```python
@order_bp.route('/orders/<int:id>', methods=['GET'])
def get_order(id):
    # 查询 Order by id
    # 不存在返回 404
    # 序列化订单（serialize_order(order, include_items=True)）
    # 返回 200 + {"status": "ok", "data": {order + items}}
```

#### GET /orders — 订单筛选
```python
@order_bp.route('/orders', methods=['GET'])
def list_orders():
    # 从 request.args 获取 user_id, status（可选）
    # 构建 Query：Order.query
    # 如果有 user_id → .filter_by(user_id=user_id)
    # 如果有 status → .filter_by(status=status)
    # 返回 200 + {"status": "ok", "data": [...]}
    # 无匹配时返回 {"status": "ok", "data": []}
```

#### POST /orders/<id>/pay — 支付
```python
@order_bp.route('/orders/<int:id>/pay', methods=['POST'])
def pay_order(id):
    # 1. 获取 Idempotency-Key header
    #    - 缺失 → 400
    # 2. 查询 Order by id → 不存在返回 404
    # 3. 检查幂等性：查询 PaymentRequest where idempotency_key = key AND order_id = id
    #    - 已存在 → 直接返回该订单当前状态（不重复处理）
    # 4. 校验状态 == 'pending'（使用 validate_transition(order.status, 'pay')）→ 否则返回 409
    # 5. 扣减库存：遍历 order.items，product.stock -= item.quantity
    # 6. 更新 Order：status='paid', paid_at=datetime.utcnow()
    # 7. 创建 PaymentRequest 记录（status='paid'）
    # 8. db.session.commit()
    # 9. 返回 200 + {"status": "ok", "data": {order}}
```

#### POST /orders/<id>/ship — 发货
```python
@order_bp.route('/orders/<int:id>/ship', methods=['POST'])
def ship_order(id):
    # 查询 Order → 404
    # 校验 validate_transition(order.status, 'ship') → 失败返回 409
    # 更新：status='shipped', shipped_at=datetime.utcnow()
    # db.session.commit()
    # 返回 200
```

#### POST /orders/<id>/deliver — 送达
```python
@order_bp.route('/orders/<int:id>/deliver', methods=['POST'])
def deliver_order(id):
    # 查询 Order → 404
    # 校验 validate_transition(order.status, 'deliver') → 失败返回 409
    # 更新：status='delivered', delivered_at=datetime.utcnow()
    # db.session.commit()
    # 返回 200
```

#### POST /orders/<id>/cancel — 取消
```python
@order_bp.route('/orders/<int:id>/cancel', methods=['POST'])
def cancel_order(id):
    # 查询 Order → 404
    # 校验 validate_transition(order.status, 'cancel') → 失败返回 409
    # 如果原 status == 'paid'：
    #   遍历 order.items，product.stock += item.quantity（回滚库存）
    # 更新：status='cancelled', cancelled_at=datetime.utcnow()
    # db.session.commit()
    # 返回 200
```

## 3. 关键算法逻辑

### 3.1 状态机转换矩阵

```python
VALID_TRANSITIONS = {
    'pending':  {'pay', 'cancel'},
    'paid':     {'ship', 'cancel'},
    'shipped':  {'deliver'},
    'delivered': set(),
    'cancelled': set(),
}

def validate_transition(current_status, action):
    """校验状态转换是否合法。合法返回 True，非法返回 False。"""
    return action in VALID_TRANSITIONS.get(current_status, set())
```

每个状态操作对应的转换：
- pay: pending → paid
- ship: paid → shipped
- deliver: shipped → delivered
- cancel: pending/paid → cancelled

**所有状态操作端点统一使用 `validate_transition()` 函数校验，不硬编码状态值。**

### 3.2 幂等支付流程

```
请求到达
    ↓
获取 Idempotency-Key header
    ↓ 缺失
返回 400
    ↓ 存在
查询 Order by id
    ↓ 不存在
返回 404
    ↓ 存在
检查幂等性：PaymentRequest where idempotency_key = key AND order_id = id
    ↓ 已存在（同一订单同一 key）
返回已有结果（不重复处理）
    ↓ 不存在
校验状态 == pending（使用 validate_transition）
    ↓ 不合法
返回 409
    ↓ 合法
扣减库存 + 更新订单状态 + 创建 PaymentRequest(status='paid')
    ↓
db.session.commit()
    ↓
返回 200
```

**关键设计决策**：
- 幂等查询使用 `idempotency_key + order_id` 联合匹配，防止不同订单间的 key 冲突
- 幂等检查在状态校验之前，使重复请求快速返回
- PaymentRequest 创建时直接设置 `status='paid'`，表示支付已完成

### 3.3 库存管理策略

| 操作 | 库存变化 |
|------|---------|
| 创建订单 | 不变（仅校验） |
| 支付 | stock -= quantity |
| 取消(paid) | stock += quantity |
| 取消(pending) | 不变 |

## 4. 序列化辅助函数

```python
def serialize_product(product):
    return {
        "id": product.id,
        "name": product.name,
        "price": product.price,
        "stock": product.stock
    }

def serialize_order(order, include_items=False):
    data = {
        "id": order.id,
        "user_id": order.user_id,
        "status": order.status,
        "total_amount": order.total_amount,
        "created_at": order.created_at.isoformat() if order.created_at else None
    }
    if include_items:
        data["items"] = [
            {
                "id": item.id,
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": item.unit_price
            }
            for item in order.items
        ]
    return data
```

**使用规范**：
- `GET /orders/<id>`（详情）：调用 `serialize_order(order, include_items=True)`
- `GET /orders`（列表）和 `POST /orders`（创建）：调用 `serialize_order(order)`（不含 items）
- 状态操作端点（pay/ship/deliver/cancel）：调用 `serialize_order(order)`（不含 items）

## 5. 实现计划（ATU 执行顺序）

### ATU-003: 实现商品路由 routes_product.py
- **复杂度**：S（~40行）
- **文件**：starter/routes_product.py
- **实现内容**：
  1. 导入 Product 模型和 db
  2. 实现 serialize_product 辅助函数
  3. 实现 GET /products（含空列表处理）
  4. 实现 POST /products（含 request.json 防御性检查和输入校验）
  5. 实现 GET /products/<id>（含 404 处理）

### ATU-004: 实现订单路由 routes_order.py
- **复杂度**：L（~130行）
- **文件**：starter/routes_order.py
- **实现内容**：
  1. 导入 Order, OrderItem, PaymentRequest, Product 模型和 db
  2. 实现 serialize_order 辅助函数
  3. 实现 VALID_TRANSITIONS 状态机矩阵 + validate_transition 函数
  4. 实现 POST /orders（创建订单，含 request.json 防御性检查、items 非空校验、库存校验）
  5. 实现 GET /orders/<id>（订单详情，include_items=True）
  6. 实现 GET /orders（筛选，无匹配返回空列表）
  7. 实现 POST /orders/<id>/pay（幂等支付：idempotency_key+order_id 联合查询 → 状态校验 → 库存扣减）
  8. 实现 POST /orders/<id>/ship（使用 validate_transition）
  9. 实现 POST /orders/<id>/deliver（使用 validate_transition）
  10. 实现 POST /orders/<id>/cancel（使用 validate_transition，含 paid 状态库存回滚）

## 6. 错误处理规范

所有错误响应统一格式：
```python
return jsonify({"status": "error", "message": "描述信息"}), status_code
```

| 错误场景 | HTTP 状态码 | message 示例 |
|---------|-----------|-------------|
| 请求体非 JSON | 400 | "Request body must be JSON" |
| 字段缺失 | 400 | "Missing required field: name" |
| items 为空列表 | 400 | "Items list must not be empty" |
| 商品不存在 | 400 | "Product not found: id=5" |
| 库存不足 | 400 | "Insufficient stock for product id=3" |
| 订单不存在 | 404 | "Order not found" |
| 缺少 Idempotency-Key | 400 | "Idempotency-Key header is required" |
| 非法状态转换 | 409 | "Cannot transition from pending to shipped" |

## 7. Reviewer 警告处理

### 需求分析阶段
Reviewer 未提出退回项，无警告需要规避。

### 方案设计阶段（第1轮）
以下为 Reviewer 退回项的修复记录：

| 问题 | 严重度 | 修复措施 |
|------|--------|---------|
| 幂等 key 缺少 order_id 联合查询 | S1 | 改为 `idempotency_key + order_id` 联合匹配 |
| 幂等检查与状态检查顺序不一致 | S1 | 统一为：获取 key → 查订单 → 幂等检查 → 状态校验 |
| items 为空列表未处理 | S2 | 增加空列表校验，返回 400 |
| request.json 为 None 未处理 | S2 | 所有 POST 端点增加防御性检查 |
| VALID_TRANSITIONS 未在伪代码中使用 | S3 | 统一使用 validate_transition() 函数 |
| serialize_order 的 include_items 使用不明确 | S3 | 在第4节增加使用规范说明 |
| PaymentRequest.status 使用说明缺失 | S3 | 明确创建时直接设为 'paid' |
