# 需求分析文档 (requirements.md)

## 1. 项目概述

T3 微型电商订单系统，基于 Flask + SQLAlchemy 的多模块 REST API 项目。支持产品管理、订单系统、用户 RBAC 权限控制。

## 2. 基础需求（来自 README.md）

### 2.1 用户与 RBAC

| 需求项 | 描述 |
|--------|------|
| User 模型 | 包含 id, username（唯一）, role（'admin' 或 'user'）|
| 认证机制 | 通过 HTTP Header `X-User-Id` 识别用户身份，使用 `middleware.get_current_user()` 获取当前用户（**该函数已实现**） |
| 权限控制 | 只有 `role='admin'` 的用户可以创建/修改产品 |
| 未认证处理 | 缺少 `X-User-Id` 时返回 401 |
| 权限不足处理 | 非 admin 尝试创建产品返回 403 |

### 2.2 产品管理

| 端点 | 方法 | 描述 | 权限 |
|------|------|------|------|
| `/products` | GET | 列出所有产品 | 无需认证 |
| `/products` | POST | 创建产品 | 仅 admin |

**GET /products**
- 响应格式：`{"status": "ok", "data": [{"id", "name", "price", "stock"}, ...]}`
- HTTP 状态码：200

**POST /products**
- 请求格式：`{"name": str, "price": float, "stock": int}`
- 成功响应：`{"status": "ok", "data": {...}}`，HTTP 200 或 201
- 错误响应：
  - 无 `X-User-Id` → HTTP 401
  - 非 admin → HTTP 403
  - 参数缺失或无效 → HTTP 400

### 2.3 订单系统

| 端点 | 方法 | 描述 | 权限 |
|------|------|------|------|
| `/orders` | POST | 创建订单 | 需认证（任意角色） |
| `/orders` | GET | 查看订单 | 需认证 |

**POST /orders**
- 请求格式：`{"product_id": int, "quantity": int}`
- 业务规则：
  - 下单时**必须扣减库存**，扣减量 = 请求中的 `quantity`
  - 库存不足时拒绝下单，返回 `{"status": "error", ...}`，**即使请求被拒绝，库存不得有任何变动**
  - `total_price = product.price * quantity`
- 成功响应：`{"status": "ok", "data": {"id", "user_id", "product_id", "quantity", "total_price"}}`
- 错误响应：
  - 无 `X-User-Id` → HTTP 401
  - 参数缺失/类型错误/无效 → HTTP 400
  - 产品不存在 → HTTP 400 或 404

**GET /orders**
- Admin 用户查看所有订单
- 普通用户只查看自己的订单（返回列表中每条记录的 `user_id` 字段必须等于当前请求用户的 id）
- 响应格式：`{"status": "ok", "data": [...]}`

### 2.4 数据模型

- **User**：id (PK), username (unique, not null), role (not null, 'admin'|'user')
- **Product**：id (PK), name (not null), price (float, not null), stock (int, not null)
- **Order**：id (PK), user_id (FK→User, not null), product_id (FK→Product, not null), quantity (int, not null), total_price (float, not null)。**注意：change.md 要求新增 `origin` 字段**（见 3.1 节）

## 3. 需求变更（来自 change.md）

### 3.1 订单 origin 字段

| 需求项 | 描述 |
|--------|------|
| 新增字段 | Order 模型新增 `origin` 字段（字符串类型） |
| 默认值 | `'web'` |
| 接口支持 | POST /orders 请求中可携带 `origin` 参数（可选） |
| 响应包含 | 所有订单查询/创建响应必须返回 `origin` 字段 |

### 3.2 高频下单限流

| 需求项 | 描述 |
|--------|------|
| 限流规则 | 同一用户（基于 user_id）在 10 秒内只能**成功**提交 1 笔订单 |
| 失败不计入 | 失败的订单（如库存不足）不计入限流计数 |
| 超频响应 | 返回 HTTP 状态码 `429 Too Many Requests` |
| 用户隔离 | 不同用户之间不受限流影响 |
| 实现位置 | `middleware.py` 新增限流功能，`routes_order.py` 创建订单路由调用 |

### 3.3 库存扣减原子性

| 需求项 | 描述 |
|--------|------|
| 核心要求 | 并发下单时，库存扣减必须是绝对安全的，不能出现负数库存 |
| 实现建议 | 建议使用数据库行级锁（`SELECT ... FOR UPDATE`）或类似机制保证原子性 |
| 验证范围 | 当前测试覆盖顺序多用户下单场景（stock 不能为负数）；真正的并发安全性需通过原子性实现方案保证 |

## 4. 技术约束

| 约束项 | 描述 |
|--------|------|
| 框架 | Flask + SQLAlchemy |
| 蓝图命名 | `product_bp`（产品）、`order_bp`（订单） |
| 不可修改文件 | `app.py`（Flask app 工厂 + DB 初始化） |
| 模块依赖 | routes_product.py 和 routes_order.py 需从 models.py 和 middleware.py 导入 |

## 5. 验收标准

### 5.1 产品管理

- [ ] AC-01: Admin 成功创建产品，返回 HTTP 200 或 201
- [ ] AC-02: 普通用户创建产品返回 HTTP 403
- [ ] AC-03: GET /products 返回所有产品列表，格式 `{"status": "ok", "data": [...]}`
- [ ] AC-04: 缺少 `X-User-Id` 时 POST /products 返回 HTTP 401

### 5.2 订单系统

- [ ] AC-05: 用户成功下单后，产品库存减少量 = 请求中的 quantity（例如初始 stock=5，下单 quantity=2 后，stock 应为 3）
- [ ] AC-06: 库存不足时下单返回 `{"status": "error", ...}`，且即使请求被拒绝，产品库存不得有任何变动
- [ ] AC-07: Admin 查看订单接口返回所有用户的订单
- [ ] AC-08: 普通用户查看订单接口只返回 `user_id` 等于当前请求用户 id 的订单
- [ ] AC-09: 订单 `total_price = product.price * quantity`，计算精确
- [ ] AC-10: 购买不存在的产品返回 HTTP 400 或 404
- [ ] AC-11: POST /orders 缺少 `X-User-Id` 时返回 HTTP 401

### 5.3 RBAC

- [ ] AC-12: 普通用户创建产品返回 HTTP 403（与 AC-02 一致，独立 RBAC 验证维度）
- [ ] AC-13: Admin 创建产品返回 HTTP 200 或 201（与 AC-01 一致，独立 RBAC 验证维度）

### 5.4 需求变更

- [ ] AC-14: 下单时未指定 `origin`，响应中 `origin` 字段为 `'web'`
- [ ] AC-15: 下单时指定 `origin='app'`，响应中 `origin` 字段为 `'app'`
- [ ] AC-16: 同一用户第一单成功后，10 秒内第二单返回 HTTP 429
- [ ] AC-17: 不同用户的订单请求不受限流影响，均返回成功
- [ ] AC-18: 库存不能为负数（含顺序多用户下单场景）
- [ ] AC-19: 库存为 0 的商品不能下单，返回 `{"status": "error", ...}`

### 5.5 系统约束

- [ ] AC-20: `create_app()` 返回一个 Flask app 实例，无异常抛出
- [ ] AC-21: `create_app()` 返回的 app 的 `url_map` 包含 `/products` 和 `/orders` 路由
