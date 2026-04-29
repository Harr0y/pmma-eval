# T2-2 订单系统 — 需求分析文档

## 1. 项目概述

实现一个基于 Flask 的订单管理系统，包含商品管理、订单 CRUD、订单状态机、库存扣减和幂等付款功能。系统采用多模块架构，代码分布在 `models.py`、`routes_product.py`、`routes_order.py` 三个文件中。

## 2. 数据模型需求

### 2.1 Product（商品）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, auto | 商品 ID |
| name | String(120) | NOT NULL | 商品名称 |
| price | Float | NOT NULL | 商品价格 |
| stock | Integer | NOT NULL, default=0 | 库存数量 |

### 2.2 Order（订单）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, auto | 订单 ID |
| user_id | String(50) | NOT NULL | 用户 ID |
| status | String(20) | NOT NULL, default='pending' | 订单状态 |
| total_amount | Float | NOT NULL, default=0.0 | 订单总金额 |
| created_at | DateTime | default=utcnow | 创建时间 |
| paid_at | DateTime | nullable | 支付时间 |
| shipped_at | DateTime | nullable | 发货时间 |
| delivered_at | DateTime | nullable | 送达时间 |
| cancelled_at | DateTime | nullable | 取消时间 |

### 2.3 OrderItem（订单项）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, auto | 订单项 ID |
| order_id | Integer | FK → order.id, NOT NULL | 所属订单 |
| product_id | Integer | FK → product.id, NOT NULL | 商品 ID |
| quantity | Integer | NOT NULL | 购买数量 |
| unit_price | Float | NOT NULL | 单价（下单时快照） |

### 2.4 PaymentRequest（付款请求）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, auto | 付款请求 ID |
| order_id | Integer | FK → order.id, NOT NULL | 所属订单 |
| idempotency_key | String(200) | NOT NULL, UNIQUE | 幂等键 |
| status | String(20) | NOT NULL, default='pending' | 付款状态 |
| created_at | DateTime | default=utcnow | 创建时间 |

## 3. 功能需求

### 3.1 商品管理（routes_product.py — 需实现）

#### FR-P1: 创建商品
- **端点**: `POST /products`
- **请求体**: `{"name": str, "price": float, "stock": int}`
- **成功响应**: HTTP 201, `{"status": "ok", "data": {"id": int, "name": str, "price": float, "stock": int}}`
- **错误响应**: HTTP 400, 缺少必要字段时返回 `{"status": "error", "message": "..."}`

#### FR-P2: 列出所有商品
- **端点**: `GET /products`
- **成功响应**: HTTP 200, `{"status": "ok", "data": [{"id": int, "name": str, "price": float, "stock": int}, ...]}`

#### FR-P3: 获取商品详情
- **端点**: `GET /products/<id>`
- **成功响应**: HTTP 200, `{"status": "ok", "data": {"id": int, "name": str, "price": float, "stock": int}}`
- **错误响应**: HTTP 404, 商品不存在时

### 3.2 订单管理（routes_order.py — 需实现）

#### FR-O1: 创建订单
- **端点**: `POST /orders`
- **请求体**: `{"user_id": str, "items": [{"product_id": int, "quantity": int}, ...]}`
- **业务规则**:
  - 校验所有商品是否存在（不存在返回 400）
  - 校验库存是否充足（不足返回 400）
  - 计算总金额：`sum(product.price * quantity)` 对所有 items
  - 创建 Order 记录（status='pending'）
  - 创建 OrderItem 记录（unit_price = product.price，下单时价格快照）
- **成功响应**: HTTP 201, `{"status": "ok", "data": {"id": int, "user_id": str, "status": "pending", "total_amount": float, "created_at": str}}`
- **错误响应**: HTTP 400, 数据无效、商品不存在或库存不足

#### FR-O2: 获取订单详情
- **端点**: `GET /orders/<id>`
- **业务规则**: 返回订单信息及其所有订单项
- **成功响应**: HTTP 200, `{"status": "ok", "data": {"id": int, "user_id": str, "status": str, "total_amount": float, "created_at": str, "items": [{"id": int, "product_id": int, "quantity": int, "unit_price": float}, ...]}}`
- **错误响应**: HTTP 404

#### FR-O3: 筛选订单
- **端点**: `GET /orders`
- **查询参数**: `user_id`（可选）, `status`（可选）
- **业务规则**: 支持按 user_id、status 单独或组合筛选
- **成功响应**: HTTP 200, `{"status": "ok", "data": [...]}`

### 3.3 订单状态机（routes_order.py — 需实现）

#### FR-SM1: 状态转换规则
```
pending → paid → shipped → delivered
pending → cancelled
paid → cancelled
```

#### FR-SM2: 支付订单（pending → paid）
- **端点**: `POST /orders/<id>/pay`
- **请求头**: `Idempotency-Key`（必须，缺失返回 400）
- **业务规则**:
  - 检查 Idempotency-Key header，缺失返回 400
  - 检查订单状态是否为 `pending`，否则返回 409
  - 查找是否已有相同 idempotency_key 的 PaymentRequest：
    - **已有**: 直接返回该 PaymentRequest 关联的订单当前状态（幂等处理，不重复扣库存）
    - **没有**: 创建 PaymentRequest，扣减商品库存，更新订单状态为 `paid`，设置 `paid_at`
- **成功响应**: HTTP 200, `{"status": "ok", "data": {"status": "paid", ...}}`
- **错误响应**: 400（无 key）/ 404（订单不存在）/ 409（状态不合法）

#### FR-SM3: 发货订单（paid → shipped）
- **端点**: `POST /orders/<id>/ship`
- **业务规则**: 仅 `paid` 状态可发货，设置 `shipped_at`
- **错误响应**: 404 / 409

#### FR-SM4: 送达订单（shipped → delivered）
- **端点**: `POST /orders/<id>/deliver`
- **业务规则**: 仅 `shipped` 状态可送达，设置 `delivered_at`
- **错误响应**: 404 / 409

#### FR-SM5: 取消订单（pending/paid → cancelled）
- **端点**: `POST /orders/<id>/cancel`
- **业务规则**:
  - 仅 `pending` 或 `paid` 状态可取消
  - 如果是 `paid` 状态，需要**回滚库存**（恢复商品 stock）
  - 设置 `cancelled_at`
- **错误响应**: 404 / 409

#### FR-SM6: 非法状态跳转
- 所有不合法的状态转换返回 HTTP 409 Conflict

### 3.4 库存管理需求

#### FR-INV1: 库存扣减时机
- 库存在**支付时**扣减，不在创建订单时扣减

#### FR-INV2: 取消回滚
- 取消 `paid` 状态订单时，恢复所有订单项对应的商品库存
- 取消 `pending` 状态订单时，不改变库存（因为未扣减过）

#### FR-INV3: 幂等扣减
- 同一 Idempotency-Key 重复请求不会重复扣减库存

### 3.5 幂等性需求

#### FR-IDM1: Idempotency-Key 必填
- 支付接口必须携带 `Idempotency-Key` header
- 缺失返回 HTTP 400

#### FR-IDM2: 相同 Key 幂等处理
- 同一 Idempotency-Key + 同一订单 的重复请求返回相同结果
- 不重复创建 PaymentRequest（利用 unique 约束）
- 不重复扣减库存

#### FR-IDM3: 不同 Key 视为不同请求
- 对已支付订单使用不同的 Idempotency-Key 再次支付，应返回 409 Conflict

## 4. 约束条件

### 4.1 架构约束
- `app.py` 不可修改（已声明）
- 必须使用 Flask Blueprint 注册路由
- 各模块通过 `from models import ...` 导入模型

### 4.2 接口约束
- 所有响应使用统一格式：`{"status": "ok", "data": ...}` 或 `{"status": "error", "message": "..."}`
- HTTP 状态码规范：200（成功）、201（创建成功）、400（客户端错误）、404（未找到）、409（冲突）

## 5. 验收标准

| 编号 | 验收标准 | 验证方式 |
|------|----------|----------|
| AC-1 | 商品 CRUD（创建、列表、详情）接口正常工作 | test_basic.py TestProductCRUD |
| AC-2 | 创建订单成功，初始状态 pending | test_basic.py TestOrderCRUD.test_create_order |
| AC-3 | 库存不足时创建订单返回 400 | test_basic.py TestOrderCRUD.test_create_order_insufficient_stock |
| AC-4 | 多商品订单总价计算正确 | test_basic.py TestOrderCRUD.test_create_order_total_calculation |
| AC-5 | 按 user_id/status 筛选订单正确 | test_basic.py TestOrderCRUD.test_filter_orders |
| AC-6 | 支付订单 pending→paid 成功 | test_basic.py TestStateMachine.test_pay_order |
| AC-7 | 发货 paid→shipped 成功 | test_basic.py TestStateMachine.test_ship_order |
| AC-8 | 送达 shipped→delivered 成功 | test_basic.py TestStateMachine.test_deliver_order |
| AC-9 | 非法跳转 pending→shipped 返回 409 | test_basic.py TestStateMachine.test_illegal_pending_to_shipped |
| AC-10 | 非法跳转 paid→delivered 返回 409 | test_basic.py TestStateMachine.test_illegal_paid_to_delivered |
| AC-11 | 已送达不可取消返回 409 | test_basic.py TestStateMachine.test_delivered_cannot_be_cancelled |
| AC-12 | 付款时扣减库存 | test_basic.py TestInventory.test_pay_deducts_stock |
| AC-13 | 取消已付款订单回滚库存 | test_basic.py TestInventory.test_cancel_paid_restores_stock |
| AC-14 | 取消 pending 订单不影响库存 | test_basic.py TestInventory.test_cancel_pending_no_stock_change |
| AC-15 | 同一 Idempotency-Key 重复付款只扣一次库存 | test_basic.py TestIdempotency.test_duplicate_pay_same_key |
| AC-16 | 不同 key 对已支付订单再次支付返回 409 | test_basic.py TestIdempotency.test_different_key_different_request |
| AC-17 | 缺少 Idempotency-Key 返回 400 | test_basic.py TestIdempotency.test_missing_idempotency_key |
