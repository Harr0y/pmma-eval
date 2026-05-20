# 需求文档 — T2-2 订单系统

## 1. 项目概述

实现一个基于 Flask 的多模块订单系统，包含商品管理和订单管理功能。订单具有完整的状态机（pending → paid → shipped → delivered / cancelled），支付支持幂等性，库存扣减在支付时执行。

## 2. 数据模型需求

### 2.1 Product（商品）
| 字段 | 类型 | 约束 |
|------|------|------|
| id | Integer | PK, auto-increment |
| name | String(120) | NOT NULL |
| price | Float | NOT NULL |
| stock | Integer | NOT NULL, default=0 |

### 2.2 Order（订单）
| 字段 | 类型 | 约束 |
|------|------|------|
| id | Integer | PK, auto-increment |
| user_id | String(50) | NOT NULL |
| status | String(20) | NOT NULL, default='pending' |
| total_amount | Float | NOT NULL, default=0.0 |
| created_at | DateTime | auto-set (utcnow) |
| paid_at | DateTime | nullable |
| shipped_at | DateTime | nullable |
| delivered_at | DateTime | nullable |
| cancelled_at | DateTime | nullable |
| items | relationship | OrderItem (lazy=True) |

### 2.3 OrderItem（订单项）
| 字段 | 类型 | 约束 |
|------|------|------|
| id | Integer | PK, auto-increment |
| order_id | Integer | FK → order.id, NOT NULL |
| product_id | Integer | FK → product.id, NOT NULL |
| quantity | Integer | NOT NULL |
| unit_price | Float | NOT NULL |

### 2.4 PaymentRequest（支付请求）
| 字段 | 类型 | 约束 |
|------|------|------|
| id | Integer | PK, auto-increment |
| order_id | Integer | FK → order.id, NOT NULL |
| idempotency_key | String(200) | NOT NULL, **UNIQUE** |
| status | String(20) | NOT NULL, default='pending' |
| created_at | DateTime | auto-set (utcnow) |

> **注意**：PaymentRequest.status 字段在当前版本中仅用于记录创建状态，支付成功后无需更新。该字段为未来扩展预留。

## 3. 订单状态机

### 3.1 有效状态值
`pending`, `paid`, `shipped`, `delivered`, `cancelled`

### 3.2 合法状态跳转
| 当前状态 | 操作 | 目标状态 |
|----------|------|----------|
| pending | pay | paid |
| paid | ship | shipped |
| shipped | deliver | delivered |
| pending | cancel | cancelled |
| paid | cancel | cancelled |

### 3.3 非法状态跳转规则

> **除 3.2 节列出的合法跳转外，所有其他状态跳转均视为非法，返回 409 Conflict。**

特别包括但不限于：
- pending → shipped（跳过 paid）
- pending → delivered（跳过 paid、shipped）
- paid → delivered（跳过 shipped）
- shipped → cancel（已发货不可取消）
- shipped → paid（逆向）
- delivered → 任何状态变更（delivered 为终态）
- cancelled → 任何状态变更（cancelled 为终态）

## 4. API 接口需求

### 4.1 商品路由（routes_product.py）

#### POST /products — 创建商品
- **请求体**: `{"name": str, "price": float, "stock": int}`
- **成功响应** (201): `{"status": "ok", "data": {"id": int, "name": str, "price": float, "stock": int}}`
- **错误响应** (400): `{"status": "error", "message": "..."}` — 必填字段缺失

#### GET /products — 列出所有商品
- **成功响应** (200): `{"status": "ok", "data": [{"id": int, "name": str, "price": float, "stock": int}, ...]}`

#### GET /products/<id> — 获取商品详情
- **成功响应** (200): `{"status": "ok", "data": {"id": int, "name": str, "price": float, "stock": int}}`
- **错误响应** (404): `{"status": "error", "message": "..."}` — 商品不存在

### 4.2 订单路由（routes_order.py）

#### POST /orders — 创建订单
- **请求体**: `{"user_id": str, "items": [{"product_id": int, "quantity": int}, ...]}`
- **业务规则**:
  - items 不得为空列表，否则返回 400
  - 校验所有 product_id 对应的商品存在（任一不存在即返回 400）
  - 若多个订单项引用同一 product_id，需**合并计算**总 quantity 后校验库存（即商品库存 >= 该商品在所有订单项中的 quantity 之和）
  - total_amount = Σ(product.price × quantity)
  - 创建 Order 和 OrderItem 记录
  - 初始状态为 `pending`
  - **注意：创建订单时不扣减库存，库存扣减在支付时进行**
- **成功响应** (201): `{"status": "ok", "data": {"id": int, "user_id": str, "status": "pending", "total_amount": float, "created_at": str}}`
- **错误响应** (400): 商品不存在、库存不足、数据格式错误

#### GET /orders/<id> — 获取订单详情
- **成功响应** (200): `{"status": "ok", "data": {"id": int, "user_id": str, "status": str, "total_amount": float, "created_at": str, "items": [{"id": int, "product_id": int, "quantity": int, "unit_price": float}, ...]}}`
- **错误响应** (404): 订单不存在

#### GET /orders — 筛选订单
- **查询参数**: `user_id` (可选), `status` (可选)
- **成功响应** (200): `{"status": "ok", "data": [{"id": int, "user_id": str, "status": str, "total_amount": float, "created_at": str}, ...]}`
- **说明**: 列表响应中**不包含** items 详情，仅返回订单摘要信息

#### POST /orders/<id>/pay — 支付订单
- **请求头**: `Idempotency-Key` (必需)
- **业务规则**:
  - 状态检查：仅 `pending` 状态可支付
  - Idempotency-Key 缺失返回 400
  - 查找 PaymentRequest 表中是否有相同 idempotency_key 的记录：
    - **已存在且关联同一 order_id**：幂等返回，返回该订单当前状态（HTTP 200），**不重复扣减库存**
    - **已存在但关联不同 order_id**：由于 idempotency_key 全局唯一（UNIQUE 约束），此情况理论上不会发生，若触发则返回 400 错误
    - **不存在**：创建 PaymentRequest 记录，执行支付逻辑（扣减库存、更新订单状态为 paid、设置 paid_at 时间戳）
- **成功响应** (200): `{"status": "ok", "data": {"id": int, "status": "paid", ...}}`
- **错误响应**:
  - 400: 缺少 Idempotency-Key
  - 404: 订单不存在
  - 409: 非法状态跳转（非 pending 状态）

#### POST /orders/<id>/ship — 发货
- **业务规则**: 仅 `paid` → `shipped`，设置 shipped_at 时间戳
- **成功响应** (200): `{"status": "ok", "data": {"id": int, "status": "shipped", ...}}`
- **错误响应**: 404 / 409

#### POST /orders/<id>/deliver — 送达
- **业务规则**: 仅 `shipped` → `delivered`，设置 delivered_at 时间戳
- **成功响应** (200): `{"status": "ok", "data": {"id": int, "status": "delivered", ...}}`
- **错误响应**: 404 / 409

#### POST /orders/<id>/cancel — 取消订单
- **业务规则**:
  - `pending` → `cancelled`：设置 cancelled_at 时间戳，**不回滚库存**（库存未扣减）
  - `paid` → `cancelled`：设置 cancelled_at 时间戳，**回滚库存**（将已扣减的库存加回）
- **成功响应** (200): `{"status": "ok", "data": {"id": int, "status": "cancelled", ...}}`
- **错误响应**: 404 / 409

## 5. 接口返回格式

所有接口统一使用以下 JSON 格式：

```json
// 成功
{"status": "ok", "data": ...}

// 错误
{"status": "error", "message": "错误描述"}
```

## 6. 验收标准

1. ✅ 所有商品 API 接口（POST/GET/GET）可正常调用
2. ✅ 所有订单 API 接口（POST/GET/GET/POST×4）可正常调用
3. ✅ 订单状态机严格遵循合法跳转规则，非法跳转返回 409
4. ✅ 支付时正确扣减库存，取消已付款订单正确回滚库存
5. ✅ Idempotency-Key 幂等性：重复 key 不重复扣库存
6. ✅ 不同 key 视为不同请求（已付款订单重复支付返回 409）
7. ✅ 缺少 Idempotency-Key 返回 400
8. ✅ `tests/test_basic.py` 中所有 19 个测试用例全部通过

## 7. 非功能需求

- **模块化**: 代码分布在 `routes_product.py` 和 `routes_order.py` 中，通过 Flask Blueprint 注册
- **模块间接口一致性**: 模型字段名、状态值、关联关系在各模块间保持一致
- **不可修改文件**: `app.py` 为 Flask 应用工厂，不得修改
