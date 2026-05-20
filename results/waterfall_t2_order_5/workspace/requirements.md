# T2-2 订单系统 — 需求分析文档

## 1. 项目概述

实现一个基于 Flask 的多模块订单系统，包含商品管理和订单全生命周期管理（创建→支付→发货→送达→取消），支持库存扣减与回滚、支付幂等性等关键业务逻辑。

## 2. 系统约束

- **app.py 不可修改** — Flask 应用工厂和 DB 初始化已固定
- **models.py 已定义** — 数据模型字段不可更改
- **多模块架构** — `routes_product.py` 和 `routes_order.py` 通过 Blueprint 注册，从 `models.py` 导入模型
- **接口返回格式** — 统一为 `{"status": "ok", "data": ...}` 或 `{"status": "error", "message": "..."}`
- **依赖** — Flask >= 3.0, Flask-SQLAlchemy >= 3.1

## 3. 数据模型需求

### 3.1 Product（商品）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, auto | 商品 ID |
| name | String(120) | NOT NULL | 商品名称 |
| price | Float | NOT NULL | 单价 |
| stock | Integer | NOT NULL, default 0 | 库存数量 |

### 3.2 Order（订单）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, auto | 订单 ID |
| user_id | String(50) | NOT NULL | 用户标识 |
| status | String(20) | NOT NULL, default 'pending' | 订单状态 |
| total_amount | Float | NOT NULL, default 0.0 | 订单总金额 |
| created_at | DateTime | auto | 创建时间 |
| paid_at | DateTime | nullable | 支付时间 |
| shipped_at | DateTime | nullable | 发货时间 |
| delivered_at | DateTime | nullable | 送达时间 |
| cancelled_at | DateTime | nullable | 取消时间 |

### 3.3 OrderItem（订单明细）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, auto | 明细 ID |
| order_id | Integer | FK → order.id, NOT NULL | 所属订单 |
| product_id | Integer | FK → product.id, NOT NULL | 商品 ID |
| quantity | Integer | NOT NULL | 购买数量 |
| unit_price | Float | NOT NULL | 下单时单价（快照） |

### 3.4 PaymentRequest（支付请求）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, auto | 请求 ID |
| order_id | Integer | FK → order.id, NOT NULL | 关联订单 |
| idempotency_key | String(200) | NOT NULL, UNIQUE | 幂等键 |
| status | String(20) | NOT NULL, default 'pending' | 支付状态 |
| created_at | DateTime | auto | 创建时间 |

**PaymentRequest.status 有效值**：`pending`（初始）→ `completed`（支付成功）

### 3.5 订单状态枚举

有效值：`pending` → `paid` → `shipped` → `delivered`，以及 `cancelled`

## 4. 功能需求

### FR-01: 商品管理路由（routes_product.py）

#### FR-01.1: 创建商品
- **端点**: `POST /products`
- **请求体**: `{"name": str, "price": float, "stock": int}`
- **成功响应**: 201, `{"status": "ok", "data": {Product 对象}}`
- **错误**: 400 — 缺少必填字段

#### FR-01.2: 列出所有商品
- **端点**: `GET /products`
- **成功响应**: 200, `{"status": "ok", "data": [{Product 对象}, ...]}`

#### FR-01.3: 获取商品详情
- **端点**: `GET /products/<id>`
- **成功响应**: 200, `{"status": "ok", "data": {Product 对象}}`
- **错误**: 404 — 商品不存在

### FR-02: 订单 CRUD 路由（routes_order.py）

#### FR-02.1: 创建订单
- **端点**: `POST /orders`
- **请求体**: `{"user_id": str, "items": [{"product_id": int, "quantity": int}, ...]}`
- **业务规则**:
  - 请求体必须包含 `user_id`（非空字符串）和 `items`（非空列表），缺失返回 400
  - 每个item的 `quantity` 必须 >= 1，否则返回 400
  - 校验所有商品是否存在，不存在返回 400
  - 校验所有商品库存是否充足（stock >= quantity），不足返回 400
  - 同一 `product_id` 出现多次时，分别创建独立的 OrderItem 记录（不合并）
  - 创建 Order（status=pending）和 OrderItem 记录
  - total_amount = Σ(product.price × quantity)
  - unit_price 使用下单时商品价格（快照）
- **成功响应**: 201, `{"status": "ok", "data": {id, user_id, status, total_amount, created_at}}`
- **错误**: 400 — 无效数据/商品不存在/库存不足

#### FR-02.2: 获取订单详情
- **端点**: `GET /orders/<id>`
- **成功响应**: 200, `{"status": "ok", "data": {Order 对象 + items: [{OrderItem 对象}, ...]}}`
- **错误**: 404 — 订单不存在

#### FR-02.3: 筛选订单列表
- **端点**: `GET /orders?user_id=X&status=Y`
- **查询参数**: user_id（可选）, status（可选），可单独或组合使用
- **无参数行为**: 不带任何查询参数时，返回所有订单
- **成功响应**: 200, `{"status": "ok", "data": [{Order 对象}, ...]}`

### FR-03: 支付（含幂等性）

#### FR-03.1: 支付订单
- **端点**: `POST /orders/<id>/pay`
- **请求头**: `Idempotency-Key`（必填）
- **业务规则**:
  - 订单必须存在，不存在返回 404
  - 订单状态必须为 `pending`，否则返回 409
  - 缺少 Idempotency-Key 返回 400
  - 检查 Idempotency-Key 是否已存在（查询 PaymentRequest 表）：
    - 已存在：返回 200, `{"status": "ok", "data": {Order 对象}}`（幂等），**不重复扣库存**
    - 不存在：执行支付逻辑
  - 执行支付：
    - 扣减每个 OrderItem 对应商品的 stock
    - 创建 PaymentRequest 记录（status='completed'）
    - 更新订单状态为 `paid`，设置 paid_at
- **成功响应**: 200, `{"status": "ok", "data": {Order 对象}}`
- **错误**: 404（订单不存在）、400（缺少 key）、409（非法状态）

### FR-04: 状态机转换

#### FR-04.1: 发货
- **端点**: `POST /orders/<id>/ship`
- **前置条件**: 订单存在（不存在返回 404）且 status == `paid`
- **后置效果**: status → `shipped`, 设置 shipped_at
- **成功响应**: 200, `{"status": "ok", "data": {Order 对象}}`
- **错误**: 404（不存在）、409（非法状态）

#### FR-04.2: 送达
- **端点**: `POST /orders/<id>/deliver`
- **前置条件**: 订单存在（不存在返回 404）且 status == `shipped`
- **后置效果**: status → `delivered`, 设置 delivered_at
- **成功响应**: 200, `{"status": "ok", "data": {Order 对象}}`
- **错误**: 404（不存在）、409（非法状态）

#### FR-04.3: 取消
- **端点**: `POST /orders/<id>/cancel`
- **前置条件**: 订单存在（不存在返回 404）且 status == `pending` 或 `paid`
- **后置效果**: status → `cancelled`, 设置 cancelled_at
- **库存回滚**: 仅当当前 status == `paid` 时，恢复每个 OrderItem 对应商品的 stock（stock += quantity）
- **已取消不可重复取消**: `cancelled` 状态再次取消返回 409
- **成功响应**: 200, `{"status": "ok", "data": {Order 对象}}`
- **错误**: 404（不存在）、409（非法状态，含 delivered、shipped、cancelled 状态）

## 5. 状态转换矩阵

### 5.1 订单存在时的状态转换

| 当前状态 \ 操作 | pay | ship | deliver | cancel |
|----------------|-----|------|---------|--------|
| pending | ✅ paid | ❌ 409 | ❌ 409 | ✅ cancelled |
| paid | ❌ 409 | ✅ shipped | ❌ 409 | ✅ cancelled（回滚库存） |
| shipped | ❌ 409 | ❌ 409 | ✅ delivered | ❌ 409 |
| delivered | ❌ 409 | ❌ 409 | ❌ 409 | ❌ 409 |
| cancelled | ❌ 409 | ❌ 409 | ❌ 409 | ❌ 409 |

### 5.2 订单不存在时

所有状态转换操作（pay/ship/deliver/cancel）对不存在的订单 ID 均返回 404。

## 6. 验收标准

### AC-01: 商品接口
- [ ] POST /products 创建商品返回 201
- [ ] GET /products 返回商品列表
- [ ] GET /products/<id> 返回商品详情
- [ ] GET /products/<id> 商品不存在返回 404

### AC-02: 订单 CRUD
- [ ] POST /orders 创建订单成功，状态为 pending
- [ ] POST /orders 库存不足返回 400
- [ ] POST /orders 多商品订单 total_amount 计算正确
- [ ] GET /orders/<id> 返回订单详情（含 items 列表）
- [ ] GET /orders/<id> 订单不存在返回 404
- [ ] GET /orders?user_id=X 按 user_id 筛选
- [ ] GET /orders?status=Y 按 status 筛选
- [ ] GET /orders 无参数返回所有订单

### AC-03: 状态机
- [ ] pending → paid 成功
- [ ] paid → shipped 成功
- [ ] shipped → delivered 成功
- [ ] pending → shipped 返回 409（非法跳转）
- [ ] paid → delivered 返回 409（非法跳转）
- [ ] delivered → cancel 返回 409（已送达不可取消）

### AC-04: 库存管理
- [ ] 付款时扣减商品库存
- [ ] 取消已付款订单恢复库存
- [ ] 取消 pending 订单不影响库存

### AC-05: 支付幂等性
- [ ] 同一 Idempotency-Key 重复请求只扣一次库存
- [ ] 不同 Idempotency-Key 对已付款订单返回 409
- [ ] 缺少 Idempotency-Key 返回 400

## 7. 测试用例覆盖

test_basic.py 共 19 个测试用例：
- TestProductCRUD: 3 个（create, list, get）
- TestOrderCRUD: 4 个（create, insufficient_stock, total_calculation, filter）
- TestStateMachine: 6 个（pay, ship, deliver, illegal_pending_to_shipped, illegal_paid_to_delivered, delivered_cannot_cancel）
- TestInventory: 3 个（pay_deducts_stock, cancel_paid_restores_stock, cancel_pending_no_stock_change）
- TestIdempotency: 3 个（duplicate_same_key, different_key, missing_key）
