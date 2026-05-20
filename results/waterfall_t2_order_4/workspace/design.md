# 设计文档 — T2-2 订单系统

## 1. 数据库设计

### 1.1 表结构（由 models.py 定义，已实现，不可修改）

| 表名 | 说明 |
|------|------|
| product | 商品表 |
| order | 订单表 |
| order_item | 订单项表 |
| payment_request | 支付请求表（幂等性） |

### 1.2 关键约束

- `payment_request.idempotency_key` 具有 UNIQUE 约束，确保全局唯一
- `order_item.order_id` → `order.id` 外键关联
- `order_item.product_id` → `product.id` 外键关联
- `payment_request.order_id` → `order.id` 外键关联

### 1.3 索引（隐含）

- `order.user_id` — 用于订单筛选查询
- `order.status` — 用于订单筛选查询
- `payment_request.idempotency_key` — UNIQUE 索引

## 2. API 端点设计

### 2.1 商品路由（routes_product.py）

Blueprint: `product_bp`

| 方法 | 路径 | 功能 | 状态码 |
|------|------|------|--------|
| POST | /products | 创建商品 | 201 / 400 |
| GET | /products | 列出所有商品 | 200 |
| GET | /products/\<id\> | 获取商品详情 | 200 / 404 |

**实现要点**：
- POST /products：从 `request.get_json()` 获取 name, price, stock；校验三个字段均存在；创建 Product 并 db.session.add + commit
- GET /products：`Product.query.all()`，序列化返回
- GET /products/\<id\>：`Product.query.get(id)`，不存在返回 404

### 2.2 订单路由（routes_order.py）

Blueprint: `order_bp`

| 方法 | 路径 | 功能 | 状态码 |
|------|------|------|--------|
| POST | /orders | 创建订单 | 201 / 400 |
| GET | /orders/\<id\> | 获取订单详情（含 items） | 200 / 404 |
| GET | /orders | 筛选订单 | 200 |
| POST | /orders/\<id\>/pay | 支付 | 200 / 400 / 404 / 409 |
| POST | /orders/\<id\>/ship | 发货 | 200 / 404 / 409 |
| POST | /orders/\<id\>/deliver | 送达 | 200 / 404 / 409 |
| POST | /orders/\<id\>/cancel | 取消 | 200 / 404 / 409 |

## 3. 关键算法逻辑

### 3.1 创建订单（POST /orders）

```
输入: {user_id: str, items: [{product_id: int, quantity: int}, ...]}

1. 校验 items 非空
2. 对每个 item：
   a. 查询 Product.query.get(product_id)
   b. 不存在 → 返回 400
3. 合并同 product_id 的 quantity
4. 对每个（product_id, 合并后 quantity）：
   a. 检查 product.stock >= quantity
   b. 不满足 → 返回 400
5. 计算 total_amount = Σ(product.price × item.quantity)
6. 创建 Order(user_id=..., status='pending', total_amount=...)
7. 对每个 item 创建 OrderItem(order_id=..., product_id=..., quantity=..., unit_price=product.price)
8. db.session.commit()
9. 返回 201 + 订单数据（不含 items）
```

**注意**：unit_price 记录的是商品创建时的价格（快照），而非实时价格。创建订单时不扣减库存。

### 3.2 支付流程（POST /orders/\<id\>/pay）

```
输入: Header: Idempotency-Key

1. 从 request.headers 获取 Idempotency-Key
   - 缺失 → 返回 400
2. 查询 Order.query.get(id)
   - 不存在 → 返回 404
3. 查询 PaymentRequest.query.filter_by(idempotency_key=key).first()
   - 已存在 → 幂等返回，返回 200 + 订单当前数据
   - 不存在 → 继续
4. 状态检查：order.status == 'pending'
   - 不满足 → 返回 409
5. 创建 PaymentRequest(order_id=order.id, idempotency_key=key)
6. 扣减库存：遍历 order.items，product.stock -= item.quantity
7. 更新订单：order.status = 'paid', order.paid_at = datetime.utcnow()
8. db.session.commit()
9. 返回 200 + 订单数据
```

### 3.3 状态跳转验证

使用合法跳转映射表：

```python
VALID_TRANSITIONS = {
    'pending': {'pay', 'cancel'},
    'paid': {'ship', 'cancel'},
    'shipped': {'deliver'},
    'delivered': set(),      # 终态
    'cancelled': set(),      # 终态
}
```

验证逻辑：
```python
def check_transition(order, action):
    valid_actions = VALID_TRANSITIONS.get(order.status, set())
    if action not in valid_actions:
        return False  # 返回 409
    return True
```

### 3.4 取消订单库存回滚

```
POST /orders/<id>/cancel

1. 查询订单，不存在 → 404
2. 验证状态跳转：status must be in ('pending', 'paid')
   - 不满足 → 409
3. if order.status == 'paid':
   - 遍历 order.items，product.stock += item.quantity（回滚库存）
4. order.status = 'cancelled', order.cancelled_at = datetime.utcnow()
5. db.session.commit()
6. 返回 200
```

### 3.5 序列化辅助函数

```python
def serialize_product(p):
    return {"id": p.id, "name": p.name, "price": p.price, "stock": p.stock}

def serialize_order(o, include_items=False):
    data = {
        "id": o.id,
        "user_id": o.user_id,
        "status": o.status,
        "total_amount": o.total_amount,
        "created_at": o.created_at.isoformat() if o.created_at else None
    }
    if include_items:
        data["items"] = [
            {"id": i.id, "product_id": i.product_id, "quantity": i.quantity, "unit_price": i.unit_price}
            for i in o.items
        ]
    return data
```

## 4. 幂等性方案

### 4.1 设计决策

- 使用 PaymentRequest 表的 `idempotency_key`（UNIQUE 约束）实现幂等
- 每次支付请求先查询是否存在相同 key 的 PaymentRequest
- 存在 → 直接返回已处理结果（幂等），不重复执行业务逻辑
- 不存在 → 创建新 PaymentRequest 记录 + 执行支付逻辑

### 4.2 边界情况

- **跨订单 key 冲突**：由于 idempotency_key 全局唯一，理论上不会出现同 key 绑定不同订单的情况
- **不同 key 重复支付**：已付款订单使用新 key 再次支付 → 状态检查失败，返回 409

## 5. 实现计划（ATU 拆分和执行顺序）

### 执行顺序

```
ATU-003 (routes_product.py)  ──┐
                                ├──→ ATU-007 (测试验证) → ATU-008 (交付)
ATU-004 (订单 CRUD) ──→ ATU-005 (支付幂等) ──→ ATU-006 (状态机) ──┘
```

### ATU-003: 实现商品路由 routes_product.py
- **文件**: `starter/routes_product.py`
- **内容**: 3 个端点（POST/GET/GET）
- **依赖**: 无（仅依赖已实现的 models.py）
- **预估**: ~30 行

### ATU-004: 实现订单 CRUD 路由
- **文件**: `starter/routes_order.py`
- **内容**: POST /orders、GET /orders/\<id\>、GET /orders（筛选）
- **依赖**: models.py, routes_product.py（序列化函数）
- **预估**: ~60 行
- **包含**: 序列化辅助函数、创建订单逻辑（含库存校验和总价计算）

### ATU-005: 实现支付与幂等性
- **文件**: `starter/routes_order.py`
- **内容**: POST /orders/\<id\>/pay
- **依赖**: ATU-004（订单模型和序列化函数）
- **预估**: ~30 行
- **包含**: Idempotency-Key 校验、PaymentRequest 查询/创建、库存扣减、状态更新

### ATU-006: 实现状态机（发货/送达/取消）
- **文件**: `starter/routes_order.py`
- **内容**: POST /orders/\<id\>/ship、deliver、cancel
- **依赖**: ATU-005（VALID_TRANSITIONS 映射表）
- **预估**: ~40 行
- **包含**: 状态跳转验证函数、发货/送达/取消逻辑、库存回滚

## 6. 模块间接口

### 6.1 routes_product.py 导出
- `product_bp` — Flask Blueprint

### 6.2 routes_order.py 导出
- `order_bp` — Flask Blueprint

### 6.3 共享依赖
- 两者均从 `models.py` 导入 SQLAlchemy 模型
- 两者均从 `app.py` 导入 `db`（通过 models.py 间接导入）
- routes_order.py 需要操作 `Product.stock`（跨模块数据访问）

## 7. 错误处理策略

### 7.1 统一错误响应格式

```python
def error_response(message, status_code):
    return jsonify({"status": "error", "message": message}), status_code
```

### 7.2 错误码映射

| 场景 | HTTP 状态码 | 说明 |
|------|------------|------|
| 资源不存在 | 404 | 商品/订单不存在 |
| 请求参数错误 | 400 | 缺少必填字段、库存不足、缺少 Idempotency-Key |
| 状态冲突 | 409 | 非法状态跳转 |
| 创建成功 | 201 | POST 创建资源 |
| 操作成功 | 200 | GET/状态变更操作 |
