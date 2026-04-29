# 需求规格说明书 — T3 微型电商订单系统

## 1. 项目概述

基于 Flask + SQLAlchemy 构建的多模块微型电商订单系统，支持用户 RBAC、产品管理、订单处理，以及双十一大促场景下的并发控制和渠道追溯。

## 2. 功能需求

### 2.1 用户与 RBAC（FR-001）

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-001-1 | User 模型包含 `id`, `username`(unique), `role`('admin'/'user') 字段 | P0 |
| FR-001-2 | `middleware.get_current_user()` 从 `X-User-Id` header 获取用户对象 | P0 |
| FR-001-3 | 只有 `role='admin'` 的用户可以创建/修改产品 | P0 |
| FR-001-4 | 无 `X-User-Id` header 时返回 401 | P0 |
| FR-001-5 | 非 admin 用户尝试创建产品返回 403 | P0 |

### 2.2 产品管理（FR-002）

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-002-1 | `GET /products` 返回所有产品列表 | P0 |
| FR-002-2 | 产品列表响应格式：`{"status": "ok", "data": [{"id", "name", "price", "stock"}, ...]}` | P0 |
| FR-002-3 | `POST /products` 创建产品（仅 Admin） | P0 |
| FR-002-4 | 创建产品请求格式：`{"name": str, "price": float, "stock": int}` | P0 |
| FR-002-5 | 创建产品成功响应格式：`{"status": "ok", "data": {...}}` | P0 |
| FR-002-6 | 非 admin 创建产品返回 403 | P0 |
| FR-002-7 | 无 X-User-Id 创建产品返回 401 | P0 |

### 2.3 订单系统（FR-003）

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-003-1 | `POST /orders` 用户下单 | P0 |
| FR-003-2 | 下单请求格式：`{"product_id": int, "quantity": int}` | P0 |
| FR-003-3 | 下单时**必须扣减库存** | P0 |
| FR-003-4 | 库存不足时拒绝下单，返回 `{"status": "error", ...}` | P0 |
| FR-003-5 | `total_price = product.price * quantity` | P0 |
| FR-003-6 | `GET /orders` 查看订单列表 | P0 |
| FR-003-7 | Admin 查看所有订单 | P0 |
| FR-003-8 | 普通用户只查看自己的订单 | P0 |
| FR-003-9 | 无效 product_id 返回 400/404 | P0 |

### 2.4 需求变更：渠道追溯（FR-004 — change.md 变更1）

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-004-1 | Order 模型新增 `origin` 字段（字符串类型，默认值 `'web'`） | P0 |
| FR-004-2 | `POST /orders` 支持接收可选的 `origin` 参数 | P0 |
| FR-004-3 | 未指定 `origin` 时默认为 `'web'` | P0 |
| FR-004-4 | 所有订单查询接口必须正确返回 `origin` 字段 | P0 |

### 2.5 需求变更：高频下单限流（FR-005 — change.md 变更2）

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-005-1 | 同一用户（基于 user_id）10 秒内只能成功提交 1 笔订单 | P0 |
| FR-005-2 | 超过频率限制的请求返回 HTTP 429 Too Many Requests | P0 |
| FR-005-3 | 不同用户之间不受限流影响 | P0 |

### 2.6 需求变更：库存扣减原子性（FR-006 — change.md 变更3）

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-006-1 | 并发下单时库存扣减必须绝对安全 | P0 |
| FR-006-2 | 库存不能出现负数 | P0 |
| FR-006-3 | 库存为 0 的商品不能下单 | P0 |
| FR-006-4 | 库存不足时库存值不应被修改 | P0 |

## 3. 数据模型需求

### 3.1 User 模型

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, Auto-increment | 用户 ID |
| username | String(80) | Unique, Not Null | 用户名 |
| role | String(20) | Not Null | 角色：'admin' 或 'user' |

### 3.2 Product 模型

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, Auto-increment | 产品 ID |
| name | String(120) | Not Null | 产品名称 |
| price | Float | Not Null | 价格 |
| stock | Integer | Not Null | 库存数量 |

### 3.3 Order 模型

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, Auto-increment | 订单 ID |
| user_id | Integer | FK → user.id, Not Null | 下单用户 |
| product_id | Integer | FK → product.id, Not Null | 产品 ID |
| quantity | Integer | Not Null | 购买数量 |
| total_price | Float | Not Null | 总价 |
| origin | String | Not Null, Default 'web' | 订单来源渠道 |

## 4. 接口行为描述

### 4.1 GET /products

- **认证**：不需要
- **响应 200**：`{"status": "ok", "data": [{"id": int, "name": str, "price": float, "stock": int}, ...]}`

### 4.2 POST /products

- **认证**：需要（X-User-Id header）
- **权限**：仅 admin
- **请求体**：`{"name": str, "price": float, "stock": int}`
- **响应 200/201**：`{"status": "ok", "data": {"id": int, "name": str, "price": float, "stock": int}}`
- **响应 401**：缺少 X-User-Id 或用户不存在
- **响应 403**：用户非 admin

### 4.3 POST /orders

- **认证**：需要（X-User-Id header）
- **限流**：同一用户 10 秒内只能成功提交 1 笔
- **请求体**：`{"product_id": int, "quantity": int, "origin": str(可选)}`
- **响应 200/201**：`{"status": "ok", "data": {"id": int, "user_id": int, "product_id": int, "quantity": int, "total_price": float, "origin": str}}`
- **响应 400/404**：product_id 不存在或参数无效
- **响应 401**：缺少 X-User-Id 或用户不存在
- **响应 429**：触发限流

### 4.4 GET /orders

- **认证**：需要（X-User-Id header）
- **权限**：Admin 看全部，普通用户看自己的
- **响应 200**：`{"status": "ok", "data": [{"id": int, "user_id": int, "product_id": int, "quantity": int, "total_price": float, "origin": str}, ...]}`
- **响应 401**：缺少 X-User-Id 或用户不存在

## 5. 技术约束

- 框架：Flask + SQLAlchemy
- `app.py` 不可修改（已声明）
- Blueprint 名称：`product_bp`（产品路由）、`order_bp`（订单路由）
- 所有模块间接口（函数签名、模型字段名、Blueprint 名称）必须保持一致
- 数据库：SQLite（开发）/ 内存数据库（测试）

## 6. 验收标准

### AC-01：产品管理
- [ ] AC-01-1：Admin 成功创建产品，返回 200/201 + status ok
- [ ] AC-01-2：普通用户创建产品返回 403
- [ ] AC-01-3：GET /products 返回所有产品列表
- [ ] AC-01-4：缺少 X-User-Id 创建产品返回 400/401

### AC-02：订单系统
- [ ] AC-02-1：用户成功下单，库存正确扣减
- [ ] AC-02-2：库存不足时拒绝下单，返回 status error，库存不变
- [ ] AC-02-3：total_price = price * quantity 计算正确
- [ ] AC-02-4：Admin 查看所有订单
- [ ] AC-02-5：普通用户只看自己的订单
- [ ] AC-02-6：购买不存在产品返回 400/404

### AC-03：需求变更 — 渠道追溯
- [ ] AC-03-1：未指定 origin 时默认为 'web'
- [ ] AC-03-2：可指定自定义 origin（如 'app'）
- [ ] AC-03-3：订单查询接口正确返回 origin

### AC-04：需求变更 — 限流
- [ ] AC-04-1：同一用户 10 秒内第二单返回 429
- [ ] AC-04-2：不同用户不受限流影响

### AC-05：需求变更 — 库存原子性
- [ ] AC-05-1：库存不能为负数
- [ ] AC-05-2：库存为 0 的商品不能下单

## 7. 隐含需求与边界条件

- **输入验证**：price/stock 必须为正数，quantity 必须 ≥ 1
- **并发安全**：库存扣减需要原子性保证（使用数据库锁或条件更新）
- **数据完整性**：Order 创建失败不应影响 Product 的库存值
- **错误一致性**：所有错误响应应统一使用 `{"status": "error", "message": "..."}` 格式
