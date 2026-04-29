# 需求规格说明书 — T3 微型电商订单系统（多模块版本）

## 1. 项目概述

基于 Flask + SQLAlchemy 的多模块微型电商系统，包含产品管理、订单系统、用户 RBAC 权限控制。代码分布在多个文件中，各模块通过 import 关联。

## 2. 功能需求

### 2.1 用户与 RBAC

| 需求项 | 描述 |
|--------|------|
| User 模型 | id, username (unique), role ('admin' / 'user') |
| 认证方式 | 通过 `X-User-Id` HTTP Header 传递用户 ID |
| `get_current_user()` | 从 header 获取用户对象，无 header 返回 None |
| 权限规则 | 只有 admin 可以创建/修改产品 |

### 2.2 产品管理（routes_product.py）

| 接口 | 方法 | 权限 | 请求体 | 响应格式 |
|------|------|------|--------|----------|
| `/products` | GET | 无 | — | `{"status": "ok", "data": [{"id", "name", "price", "stock"}, ...]}` |
| `/products` | POST | Admin | `{"name": str, "price": float, "stock": int}` | `{"status": "ok", "data": {...}}` |

**错误处理：**
- POST 无 `X-User-Id` header → 401
- POST 非 admin 用户 → 403
- POST 缺少必要字段 → 400

### 2.3 订单系统（routes_order.py）

#### POST /orders — 创建订单

| 项目 | 描述 |
|------|------|
| 权限 | 需登录（X-User-Id） |
| 请求体 | `{"product_id": int, "quantity": int, "origin": str (可选)}` |
| 响应 | `{"status": "ok", "data": {"id", "user_id", "product_id", "quantity", "total_price", "origin"}}` |
| total_price | `product.price * quantity` |
| origin | 默认值 `'web'`，可指定为 `'app'`、`'wechat'` 等 |

**业务规则：**
- 下单时**必须扣减库存**，扣减必须原子性（不能出现负数库存）
- 库存不足 → `{"status": "error", ...}`
- 产品不存在 → 400/404 错误
- quantity 必须 > 0

**限流规则（变更需求）：**
- 同一 user_id 在 10 秒内只能成功提交 1 笔订单
- 超频请求 → HTTP 429 Too Many Requests
- 不同用户互不影响

#### GET /orders — 查看订单

| 角色 | 行为 |
|------|------|
| admin | 查看所有订单 |
| user | 只看自己的订单（user_id 匹配） |
| 无 X-User-Id | 401 |

响应格式：`{"status": "ok", "data": [{"id", "user_id", "product_id", "quantity", "total_price", "origin"}, ...]}`

### 2.4 需求变更（change.md）

#### 变更 1：Order origin 字段
- Order 模型新增 `origin` 字段（String，默认 `'web'`）
- POST /orders 支持可选 `origin` 参数
- 所有订单查询接口必须返回 `origin`

#### 变更 2：高频下单限流
- 在 middleware.py 中实现限流功能
- 同一 user_id 10 秒内限 1 笔订单
- 超频返回 429

#### 变更 3：库存扣减原子性
- 并发下单时库存不能出现负数
- 必须使用数据库级别的锁或条件更新保证原子性

## 3. 数据模型需求

### 3.1 User
| 字段 | 类型 | 约束 |
|------|------|------|
| id | Integer | PK, auto-increment |
| username | String(80) | unique, not null |
| role | String(20) | not null, 'admin' or 'user' |

### 3.2 Product
| 字段 | 类型 | 约束 |
|------|------|------|
| id | Integer | PK, auto-increment |
| name | String(120) | not null |
| price | Float | not null |
| stock | Integer | not null |

### 3.3 Order
| 字段 | 类型 | 约束 |
|------|------|------|
| id | Integer | PK, auto-increment |
| user_id | Integer | FK → user.id, not null |
| product_id | Integer | FK → product.id, not null |
| quantity | Integer | not null |
| total_price | Float | not null |
| origin | String(20) | not null, default 'web' |

## 4. 模块接口约定

| 模块 | 导出 | 被谁使用 |
|------|------|----------|
| `models.py` | User, Product, Order | routes_product, routes_order, middleware |
| `middleware.py` | get_current_user(), rate_limit_order() | routes_product, routes_order |
| `routes_product.py` | product_bp (Blueprint) | app.py |
| `routes_order.py` | order_bp (Blueprint) | app.py |
| `app.py` | create_app(), db | 所有模块（不可修改） |

## 5. 验收标准

### 5.1 基础功能（test_basic.py）
- [x] 管理员可创建产品
- [x] 普通用户不能创建产品（403）
- [x] 列出所有产品
- [x] 缺少 X-User-Id 创建产品失败
- [x] 用户可下单
- [x] 下单扣减库存
- [x] 库存不足下单失败，库存不变
- [x] 管理员查看所有订单
- [x] 普通用户只看自己订单
- [x] 订单总价计算正确
- [x] 购买不存在产品失败

### 5.2 变更功能（test_change.py）
- [x] 下单默认 origin 为 'web'
- [x] 下单可指定自定义 origin
- [x] 同一用户 10 秒内快速下两单，第二单返回 429
- [x] 不同用户不受限流影响
- [x] 库存不能为负数
- [x] 库存为 0 的商品不能下单

### 5.3 非功能性需求
- app.py 的 `create_app()` 必须正常启动
- 各模块间的 import 链不能断裂
- 错误响应统一使用 `{"status": "error", ...}` 格式
