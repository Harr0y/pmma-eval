# T2-2 需求分析文档

## 1. 功能需求

### 1.1 商品管理模块（routes_product.py）

| 接口 | 方法 | 路径 | 描述 |
|------|------|------|------|
| 商品列表 | GET | /products | 返回所有商品列表 |
| 创建商品 | POST | /products | 创建新商品 |
| 商品详情 | GET | /products/\<id\> | 获取单个商品信息 |

**商品列表 GET /products**
- 返回：`{"status": "ok", "data": [{"id": int, "name": str, "price": float, "stock": int}, ...]}`
- HTTP 状态码：200

**创建商品 POST /products**
- 请求体：`{"name": str, "price": float, "stock": int}`
- 返回：`{"status": "ok", "data": {"id": int, "name": str, "price": float, "stock": int}}`
- HTTP 状态码：201（成功）、400（字段缺失或无效）
- 约束：name、price、stock 均为必填字段

**商品详情 GET /products/\<id\>**
- 返回：`{"status": "ok", "data": {"id": int, "name": str, "price": float, "stock": int}}`
- HTTP 状态码：200（成功）、404（商品不存在）

### 1.2 订单管理模块（routes_order.py）

| 接口 | 方法 | 路径 | 描述 |
|------|------|------|------|
| 创建订单 | POST | /orders | 创建新订单（初始状态 pending） |
| 订单详情 | GET | /orders/\<id\> | 获取订单详情（含 items 列表） |
| 订单筛选 | GET | /orders | 按 user_id 和/或 status 筛选 |
| 支付订单 | POST | /orders/\<id\>/pay | pending → paid，扣减库存 |
| 发货 | POST | /orders/\<id\>/ship | paid → shipped |
| 送达 | POST | /orders/\<id\>/deliver | shipped → delivered |
| 取消订单 | POST | /orders/\<id\>/cancel | pending/paid → cancelled，paid 状态回滚库存 |

#### 1.2.1 创建订单 POST /orders
- 请求体：`{"user_id": str, "items": [{"product_id": int, "quantity": int}, ...]}`
- 返回：`{"status": "ok", "data": {"id": int, "user_id": str, "status": "pending", "total_amount": float, "created_at": str}}`
- HTTP 状态码：201（成功）、400（无效数据/商品不存在/库存不足）
- 业务规则：
  - 校验所有商品存在
  - 校验库存充足（每个商品的库存 >= 对应 quantity）
  - total_amount = sum(product.price × quantity) 对所有 items 求和
  - 创建时只锁定库存信息（不扣减），状态为 pending

#### 1.2.2 订单详情 GET /orders/\<id\>
- 返回：`{"status": "ok", "data": {"id": int, "user_id": str, "status": str, "total_amount": float, "created_at": str, "items": [{"id": int, "product_id": int, "quantity": int, "unit_price": float}, ...]}}`
- HTTP 状态码：200（成功）、404（订单不存在）

#### 1.2.3 订单筛选 GET /orders
- 查询参数：user_id（可选）、status（可选），可组合使用
- 返回：`{"status": "ok", "data": [...]}`
- HTTP 状态码：200

#### 1.2.4 支付订单 POST /orders/\<id\>/pay
- 请求头：`Idempotency-Key`（**必填**，缺失返回 400）
- 返回：`{"status": "ok", "data": {"status": "paid", ...}}`
- HTTP 状态码：200（成功）、400（缺少 Idempotency-Key）、404（订单不存在）、409（非法状态转换）
- 业务规则：
  - 仅 pending → paid 合法
  - **扣减商品库存**：对每个 OrderItem 对应的 Product，stock -= quantity
  - **幂等性**：同一 Idempotency-Key 重复请求，返回相同结果，**不重复扣库存**
  - **不同 Idempotency-Key**：对已支付订单视为非法请求，返回 409
  - 创建 PaymentRequest 记录

#### 1.2.5 发货 POST /orders/\<id\>/ship
- 仅 paid → shipped 合法
- HTTP 状态码：200（成功）、404（订单不存在）、409（非法状态转换）

#### 1.2.6 送达 POST /orders/\<id\>/deliver
- 仅 shipped → delivered 合法
- HTTP 状态码：200（成功）、404（订单不存在）、409（非法状态转换）

#### 1.2.7 取消订单 POST /orders/\<id\>/cancel
- 仅 pending → cancelled 和 paid → cancelled 合法
- shipped、delivered、cancelled 状态不可取消（返回 409）
- **paid 状态取消时回滚库存**：对每个 OrderItem 对应的 Product，stock += quantity
- **pending 状态取消不影响库存**（创建时未扣减）
- HTTP 状态码：200（成功）、404（订单不存在）、409（非法状态转换）

### 1.3 状态机

```
                  ┌──────────┐
                  │ pending  │
                  └────┬─────┘
                       │ pay
                       ▼
                  ┌──────────┐
          cancel │  paid    │ ship
         (rollback)│         │
                  └────┬─────┘
                       │
                       ▼
                  ┌──────────┐
                  │ shipped  │
                  └────┬─────┘
                       │ deliver
                       ▼
                  ┌──────────┐
                  │delivered │
                  └──────────┘

  cancel: pending → cancelled, paid → cancelled
```

**有效状态值**：`pending`, `paid`, `shipped`, `delivered`, `cancelled`

**合法状态转换表**：

| 当前状态 | 目标状态 | 操作 | 合法 |
|---------|---------|------|------|
| pending | paid | pay | ✅ |
| pending | cancelled | cancel | ✅ |
| paid | shipped | ship | ✅ |
| paid | cancelled | cancel | ✅（回滚库存） |
| shipped | delivered | deliver | ✅ |
| pending | shipped | ship | ❌ 409 |
| paid | delivered | deliver | ❌ 409 |
| delivered | cancelled | cancel | ❌ 409 |
| shipped | cancelled | cancel | ❌ 409（隐含） |
| cancelled | * | 任何操作 | ❌ 409（隐含） |

## 2. 数据模型需求

### 2.1 Product（商品）
| 字段 | 类型 | 约束 |
|------|------|------|
| id | Integer | PK, auto-increment |
| name | String(120) | NOT NULL |
| price | Float | NOT NULL |
| stock | Integer | NOT NULL, default 0 |

### 2.2 Order（订单）
| 字段 | 类型 | 约束 |
|------|------|------|
| id | Integer | PK, auto-increment |
| user_id | String(50) | NOT NULL |
| status | String(20) | NOT NULL, default 'pending' |
| total_amount | Float | NOT NULL, default 0.0 |
| created_at | DateTime | auto UTC |
| paid_at | DateTime | nullable |
| shipped_at | DateTime | nullable |
| delivered_at | DateTime | nullable |
| cancelled_at | DateTime | nullable |

关联：items → OrderItem (1:N)

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
| idempotency_key | String(200) | NOT NULL, UNIQUE |
| status | String(20) | NOT NULL, default 'pending' |
| created_at | DateTime | auto UTC |

## 3. 接口返回格式规范

**成功响应**：
```json
{"status": "ok", "data": ...}
```

**错误响应**：
```json
{"status": "error", "message": "错误描述"}
```

## 4. 关键业务规则

1. **库存扣减时机**：支付时（pay）扣减，非创建时
2. **库存回滚**：已支付订单取消时回滚库存，pending 取消不影响
3. **幂等性**：支付接口通过 Idempotency-Key header 实现幂等，相同 key 不重复处理
4. **库存校验**：创建订单时校验库存充足，但不扣减
5. **总价计算**：创建时基于商品当前价格快照到 unit_price

## 5. 验收标准

1. ✅ 所有 7 个订单 API 接口可正常调用
2. ✅ 所有 3 个商品 API 接口可正常调用
3. ✅ tests/test_basic.py 中所有测试用例通过
4. ✅ 状态机非法转换返回 409
5. ✅ 幂等支付正确（相同 key 不重复扣库存，不同 key 返回 409）
6. ✅ 库存扣减和回滚逻辑正确
7. ✅ 输入验证（缺少字段、商品不存在、库存不足等）返回 400
