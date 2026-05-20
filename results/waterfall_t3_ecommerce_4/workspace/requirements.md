# 需求分析文档 — T3 微型电商订单系统

## 1. 项目概述

本项目是一个基于 Flask + SQLAlchemy 的微型电商订单系统，采用多模块架构。系统支持产品管理、订单管理、用户 RBAC 权限控制，以及需求变更中新增的订单渠道追溯、高频限流、原子库存扣减功能。

**约束条件**：
- `app.py` 为应用工厂，不可修改
- 代码分布在多个文件中，模块间存在 import 依赖
- Blueprint 名称必须与 `app.py` 中的注册名称一致：`product_bp`、`order_bp`

## 2. 功能需求列表

### FR-1: 用户与 RBAC（middleware.py + models.py）

| 编号 | 需求描述 | 优先级 |
|------|---------|--------|
| FR-1.1 | User 模型包含 `id`、`username`（唯一）、`role`（'admin' 或 'user'）字段 | P0 |
| FR-1.2 | `get_current_user()` 从 `X-User-Id` 请求头获取当前用户 | P0 |
| FR-1.3 | 只有 admin 角色可以创建和修改产品 | P0 |
| FR-1.4 | 缺少 `X-User-Id` 时返回 401 | P0 |

### FR-2: 产品管理（routes_product.py）

| 编号 | 需求描述 | 优先级 |
|------|---------|--------|
| FR-2.1 | `GET /products` 返回所有产品列表 | P0 |
| FR-2.2 | `POST /products` 创建新产品（仅 admin） | P0 |
| FR-2.3 | 产品列表响应格式：`{"status": "ok", "data": [{"id", "name", "price", "stock"}, ...]}` | P0 |
| FR-2.4 | 创建产品请求格式：`{"name": str, "price": float, "stock": int}` | P0 |
| FR-2.5 | 非 admin 创建产品返回 403 | P0 |
| FR-2.6 | 无 `X-User-Id` 创建产品返回 401 | P0 |

### FR-3: 订单系统（routes_order.py）

| 编号 | 需求描述 | 优先级 |
|------|---------|--------|
| FR-3.1 | `POST /orders` 创建订单，请求：`{"product_id": int, "quantity": int}` | P0 |
| FR-3.2 | 下单时必须扣减库存 | P0 |
| FR-3.3 | 库存不足时拒绝下单，返回 `{"status": "error", ...}` | P0 |
| FR-3.4 | `total_price = product.price * quantity` | P0 |
| FR-3.5 | `GET /orders` 查看订单列表 | P0 |
| FR-3.6 | Admin 查看所有订单，普通用户只看自己的 | P0 |
| FR-3.7 | 购买不存在的产品返回 400/404 | P0 |

### FR-4: 需求变更 — 订单 origin 字段

| 编号 | 需求描述 | 优先级 |
|------|---------|--------|
| FR-4.1 | Order 模型新增 `origin` 字段（字符串），默认值 `'web'` | P0 |
| FR-4.2 | `POST /orders` 支持接收 `origin` 参数（可选） | P0 |
| FR-4.3 | 所有订单查询接口返回 `origin` 字段 | P0 |

### FR-5: 需求变更 — 高频下单限流

| 编号 | 需求描述 | 优先级 |
|------|---------|--------|
| FR-5.1 | 同一用户（user_id）在 10 秒内只能成功提交 1 笔订单 | P0 |
| FR-5.2 | 超过频率的请求返回 HTTP 429 Too Many Requests | P0 |
| FR-5.3 | 不同用户之间限流互不影响 | P0 |

### FR-6: 需求变更 — 库存扣减原子性

| 编号 | 需求描述 | 优先级 |
|------|---------|--------|
| FR-6.1 | 并发下单时库存扣减必须绝对安全，不能出现负数库存 | P0 |
| FR-6.2 | 库存为 0 的商品不能下单 | P0 |

## 3. 数据模型需求

### 3.1 User 模型（已有）
- `id`: Integer, Primary Key
- `username`: String(80), Unique, Not Null
- `role`: String(20), Not Null — 取值 'admin' 或 'user'

### 3.2 Product 模型（已有）
- `id`: Integer, Primary Key
- `name`: String(120), Not Null
- `price`: Float, Not Null
- `stock`: Integer, Not Null

### 3.3 Order 模型（需新增 origin 字段）
- `id`: Integer, Primary Key
- `user_id`: Integer, FK to User, Not Null
- `product_id`: Integer, FK to Product, Not Null
- `quantity`: Integer, Not Null
- `total_price`: Float, Not Null
- `origin`: String(20), Not Null, Default 'web' — **新增**

## 4. 接口行为描述

### 4.1 GET /products
- **权限**：无需认证
- **请求**：无参数
- **成功响应**：200 `{"status": "ok", "data": [{"id": int, "name": str, "price": float, "stock": int}, ...]}`
- **错误**：无

### 4.2 POST /products
- **权限**：Admin only
- **请求**：`{"name": str, "price": float, "stock": int}`
- **成功响应**：200/201 `{"status": "ok", "data": {"id": int, "name": str, "price": float, "stock": int}}`
- **错误**：
  - 401：缺少 `X-User-Id` header
  - 403：非 admin 用户
  - 400：缺少必填字段或字段类型错误

### 4.3 POST /orders
- **权限**：已认证用户
- **请求**：`{"product_id": int, "quantity": int, "origin": str（可选，默认 "web"）}`
- **成功响应**：200/201 `{"status": "ok", "data": {"id": int, "user_id": int, "product_id": int, "quantity": int, "total_price": float, "origin": str}}`
- **错误**：
  - 401：缺少 `X-User-Id` header
  - 400：缺少必填字段、产品不存在、quantity <= 0
  - `{"status": "error", ...}`：库存不足（HTTP 状态码可为 400）
  - 429：触发限流（10 秒内重复下单）

### 4.4 GET /orders
- **权限**：已认证用户
- **请求**：无参数
- **成功响应**：200 `{"status": "ok", "data": [{"id": int, "user_id": int, "product_id": int, "quantity": int, "total_price": float, "origin": str}, ...]}`
- **数据过滤**：Admin 返回所有订单，普通用户仅返回 `user_id` 匹配的订单
- **错误**：
  - 401：缺少 `X-User-Id` header

## 5. 验收标准

### AC-1: 产品管理
- [ ] Admin 可以成功创建产品（200/201）
- [ ] 普通用户创建产品被拒绝（403）
- [ ] 缺少 X-User-Id 创建产品被拒绝（400/401）
- [ ] 所有人可以列出产品
- [ ] 产品列表返回正确的数据格式

### AC-2: 订单系统
- [ ] 用户可以成功下单（200/201）
- [ ] 下单时库存正确扣减
- [ ] 库存不足时下单失败（status: "error"）
- [ ] 库存不足时库存不变
- [ ] Admin 查看所有订单
- [ ] 普通用户只看自己的订单
- [ ] 订单 total_price 计算正确
- [ ] 购买不存在的产品返回 400/404

### AC-3: 需求变更
- [ ] 下单不指定 origin 时默认为 'web'
- [ ] 下单可自定义 origin
- [ ] 同一用户 10 秒内第二单返回 429
- [ ] 不同用户不受限流影响
- [ ] 库存不能为负数
- [ ] 库存为 0 的商品不能下单

### AC-4: 系统约束
- [ ] app.py 未被修改
- [ ] Blueprint 名称与 app.py 注册一致
- [ ] create_app() 正常启动
- [ ] 所有模块间 import 正确

## 6. 非功能需求
- 代码结构清晰，模块职责单一
- 适当的错误处理和输入验证
- 库存扣减具备原子性保证
