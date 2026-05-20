# T3：微型电商订单系统（多模块版本）

## 项目结构

```
starter/
  app.py              # Flask app 工厂 + DB 初始化（请勿修改）
  models.py           # 数据模型（User, Product, Order）—— 需要完善
  routes_product.py   # 产品管理路由 —— 需要实现
  routes_order.py     # 订单管理路由 —— 需要实现
  middleware.py        # 认证中间件 —— 需要完善
  requirements.txt    # 依赖
```

## 重要提示

这是一个**多模块项目**，代码分布在多个文件中。各模块之间有 import 依赖：
- `routes_product.py` 和 `routes_order.py` 需要从 `models.py` 导入模型
- 所有路由模块需要从 `middleware.py` 导入认证函数
- `app.py` 负责组装所有模块（请勿修改）

**请确保各模块之间的接口（函数签名、模型字段名、Blueprint 名称）保持一致。**

## 功能要求

### 1. 用户与 RBAC（middleware.py + models.py）
- User 模型已有 `role` 字段：'admin' 或 'user'
- `middleware.get_current_user()` 已实现：从 `X-User-Id` header 获取用户
- 只有 admin 可以创建/修改产品

### 2. 产品管理（routes_product.py）
- `GET /products` → 列出所有产品
  - Response: `{"status": "ok", "data": [{"id", "name", "price", "stock"}, ...]}`
- `POST /products` → 创建产品（Admin only）
  - Request: `{"name": str, "price": float, "stock": int}`
  - Response: `{"status": "ok", "data": {...}}`
  - 非 admin 返回 403，无 X-User-Id 返回 401

### 3. 订单系统（routes_order.py）
- `POST /orders` → 用户下单
  - Request: `{"product_id": int, "quantity": int}`
  - 下单时**必须扣减库存**
  - 库存不足时拒绝，返回 `{"status": "error", ...}`
  - `total_price = product.price * quantity`
- `GET /orders` → 查看订单
  - Admin 看所有订单，普通用户只看自己的
  - Response: `{"status": "ok", "data": [...]}`

### 4. 数据模型（models.py）
- User 模型已定义，**可能需要调整**以支持新需求
- Product 模型已定义
- Order 模型已定义，**可能需要新增字段**以支持变更需求

## 技术要求
- 使用 Flask + SQLAlchemy（已配置）
- 每个路由模块注册为 Blueprint（routes_product 用 `product_bp`，routes_order 用 `order_bp`）
- 需要完善的错误处理（400, 401, 403, 404）

## 需求变更预警
该项目在执行中途可能会有需求变更，请做好模块化设计以便快速重规划。
