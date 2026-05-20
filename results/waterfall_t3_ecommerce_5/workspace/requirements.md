# 需求文档 — T3 微型电商订单系统（多模块版本）

## 1. 功能需求列表

### 1.1 用户与 RBAC（基于角色的访问控制）

| 编号 | 需求 | 优先级 |
|------|------|--------|
| FR-001 | User 模型包含 `role` 字段，值为 `'admin'` 或 `'user'` | P0 |
| FR-002 | 系统初始化时自动创建 `admin`（admin 角色）和 `user1`（user 角色）两个种子用户 | P0 |
| FR-003 | `middleware.get_current_user()` 从请求头 `X-User-Id` 获取当前用户 | P0 |
| FR-004 | 只有 `admin` 角色可以创建和修改产品 | P0 |
| FR-005 | 非 admin 用户尝试创建产品时返回 HTTP 403 | P0 |
| FR-006 | 缺少 `X-User-Id` 请求头时返回 HTTP 401 | P0 |

### 1.2 产品管理

| 编号 | 需求 | 优先级 |
|------|------|--------|
| FR-010 | `GET /products` 返回所有产品列表 | P0 |
| FR-011 | 产品列表返回格式：`{"status": "ok", "data": [{"id", "name", "price", "stock"}, ...]}` | P0 |
| FR-012 | `POST /products` 创建新产品（仅 admin） | P0 |
| FR-013 | 创建产品请求体：`{"name": str, "price": float, "stock": int}` | P0 |
| FR-014 | 创建产品成功响应：`{"status": "ok", "data": {...}}` | P0 |
| FR-015 | `GET /products` 不需要认证即可访问 | P0 |

### 1.3 订单系统

| 编号 | 需求 | 优先级 |
|------|------|--------|
| FR-020 | `POST /orders` 创建订单 | P0 |
| FR-021 | 创建订单请求体：`{"product_id": int, "quantity": int}` | P0 |
| FR-022 | 创建订单时**必须扣减库存**（原子性保证，防止超卖） | P0 |
| FR-023 | 库存不足时拒绝下单，返回 `{"status": "error", ...}` | P0 |
| FR-024 | `total_price = product.price * quantity` | P0 |
| FR-025 | 购买不存在的产品返回 HTTP 400/404 | P0 |
| FR-026 | `GET /orders` 查看订单列表 | P0 |
| FR-027 | Admin 查看所有订单 | P0 |
| FR-028 | 普通用户仅查看自己的订单（按 `user_id` 过滤） | P0 |

### 1.4 需求变更：渠道追溯与并发控制（change.md）

| 编号 | 需求 | 优先级 |
|------|------|--------|
| CHG-001 | Order 模型新增 `origin` 字段（字符串，默认值 `'web'`） | P0 |
| CHG-002 | 创建订单接口支持可选 `origin` 参数 | P0 |
| CHG-003 | 未指定 `origin` 时默认为 `'web'` | P0 |
| CHG-004 | 订单查询接口必须返回 `origin` 字段 | P0 |
| CHG-005 | 同一用户 10 秒内只能成功提交 1 笔订单 | P0 |
| CHG-006 | 超过频率限制返回 HTTP 429 Too Many Requests | P0 |
| CHG-007 | 不同用户之间的下单不受限流影响 | P0 |
| CHG-008 | 库存扣减必须是原子的，不能出现负数库存 | P0 |

## 2. 数据模型需求

### 2.1 User 模型

| 字段 | 类型 | 约束 |
|------|------|------|
| id | Integer | 主键，自增 |
| username | String(80) | 唯一，非空 |
| role | String(20) | 非空，值为 `'admin'` 或 `'user'` |

### 2.2 Product 模型

| 字段 | 类型 | 约束 |
|------|------|------|
| id | Integer | 主键，自增 |
| name | String(120) | 非空 |
| price | Float | 非空 |
| stock | Integer | 非空 |

### 2.3 Order 模型

| 字段 | 类型 | 约束 |
|------|------|------|
| id | Integer | 主键，自增 |
| user_id | Integer | 外键 → User.id，非空 |
| product_id | Integer | 外键 → Product.id，非空 |
| quantity | Integer | 非空 |
| total_price | Float | 非空 |
| origin | String(50) | 非空，默认值 `'web'`（**变更新增**） |

## 3. 接口行为详细描述

### 3.1 `GET /products`

- **认证**：不需要认证
- **成功响应** (200)：`{"status": "ok", "data": [{"id": int, "name": str, "price": float, "stock": int}, ...]}`
- **空列表**：返回 `{"status": "ok", "data": []}`

### 3.2 `POST /products`

- **认证**：需要 `X-User-Id` 请求头
- **权限**：仅 admin 角色可访问
- **请求体**：`{"name": str, "price": float, "stock": int}`
- **成功响应** (200/201)：`{"status": "ok", "data": {"id": int, "name": str, "price": float, "stock": int}}`
- **错误响应**：
  - 401/400：缺少 `X-User-Id` 或用户不存在
  - 403：非 admin 用户
  - 400：请求体缺少必填字段

### 3.3 `POST /orders`

- **认证**：需要 `X-User-Id` 请求头
- **请求体**：`{"product_id": int, "quantity": int, "origin": str（可选，默认 "web"）}`
- **限流**：同一用户 10 秒内只能提交 1 单，超出返回 429
- **成功响应** (200/201)：`{"status": "ok", "data": {"id": int, "user_id": int, "product_id": int, "quantity": int, "total_price": float, "origin": str}}`
- **错误响应**：
  - 401/400：缺少 `X-User-Id` 或用户不存在
  - 400/404：产品不存在
  - `{"status": "error", ...}`：库存不足（库存不得扣减）
  - 429：触发限流

### 3.4 `GET /orders`

- **认证**：需要 `X-User-Id` 请求头
- **权限**：admin 返回所有订单，普通用户仅返回 `user_id` 匹配的订单
- **成功响应** (200)：`{"status": "ok", "data": [{"id": int, "user_id": int, "product_id": int, "quantity": int, "total_price": float, "origin": str}, ...]}`

## 4. 验收标准

### AC-01：产品管理
- [ ] admin 可以成功创建产品，返回 status "ok"
- [ ] 普通用户创建产品返回 403
- [ ] 缺少 X-User-Id 创建产品返回 400/401/403
- [ ] GET /products 返回所有产品列表
- [ ] 无产品时返回空列表

### AC-02：订单系统
- [ ] 用户可以成功下单，返回 status "ok"
- [ ] 下单后库存正确扣减
- [ ] 库存不足时返回 status "error"，库存不被扣减
- [ ] 订单 total_price = price × quantity 计算正确
- [ ] 购买不存在的产品返回 400/404
- [ ] admin 查看订单可看到所有订单
- [ ] 普通用户查看订单只能看到自己的

### AC-03：RBAC 权限控制
- [ ] 普通用户不能创建产品（403）
- [ ] admin 可以创建产品（200/201）

### AC-04：需求变更 — 渠道追溯
- [ ] 下单时未指定 origin，默认为 'web'
- [ ] 下单时可以指定 origin（如 'app'）
- [ ] 订单查询接口返回 origin 字段

### AC-05：需求变更 — 限流
- [ ] 同一用户 10 秒内快速下两单，第二单返回 429
- [ ] 不同用户不受限流影响

### AC-06：需求变更 — 原子库存
- [ ] 库存不能变为负数
- [ ] 库存为 0 的商品不能下单
- [ ] 并发下单不会导致超卖

## 5. 技术约束

- 使用 Flask + SQLAlchemy（已配置）
- 每个路由模块注册为 Blueprint：`product_bp` 和 `order_bp`
- 错误处理覆盖：400, 401, 403, 404, 429
- `app.py` 不得修改（框架约束）
- 限流实现基于内存（进程内字典），无需外部依赖
