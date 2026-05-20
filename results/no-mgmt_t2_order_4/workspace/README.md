# T2-2：订单系统 — 订单状态机 + 库存扣减（多模块版本）

## 项目结构

```
starter/
  app.py              # Flask app 工厂 + DB 初始化（请勿修改）
  models.py           # 数据模型（Product, Order, OrderItem, PaymentRequest）
  routes_product.py   # 商品管理路由 —— 已实现
  routes_order.py     # 订单管理路由 —— 需要实现
  requirements.txt    # 依赖
```

## 重要提示

这是一个**多模块项目**，代码分布在多个文件中。各模块之间有 import 依赖：
- `routes_product.py` 和 `routes_order.py` 需要从 `models.py` 导入模型
- `routes_order.py` 的付款逻辑需要操作 `Product` 的 `stock` 字段
- `app.py` 负责组装所有模块（请勿修改）

**请确保各模块之间的接口（模型字段名、状态值、关联关系）保持一致。**

## 功能要求

### 1. 数据模型（models.py）
- Product: id, name, price (float), stock (int)
- Order: id, user_id (string), status (string), total_amount (float), created_at, paid_at, shipped_at, delivered_at, cancelled_at
- OrderItem: id, order_id (FK), product_id (FK), quantity (int), unit_price (float)
- PaymentRequest: id, order_id (FK), idempotency_key (unique string), status, created_at
- Order status 有效值：`pending`, `paid`, `shipped`, `delivered`, `cancelled`

### 2. 商品路由（routes_product.py）— 已实现
- `GET /products` → 列出所有商品
- `POST /products` → 创建商品
- `GET /products/<id>` → 获取商品详情

### 3. 订单路由（routes_order.py）— 需要实现
使用 `order_bp = Blueprint('order_bp', __name__)`
- `POST /orders` → 创建订单 `{"user_id": "u1", "items": [{"product_id": 1, "quantity": 2}]}`
  - 校验库存，计算 total_amount，初始状态 `pending`
- `GET /orders/<id>` → 获取订单详情（含 items 列表）
- `GET /orders?user_id=X&status=Y` → 筛选订单
- `POST /orders/<id>/pay` → 支付（pending → paid）
  - 需要 `Idempotency-Key` header，缺失返回 400
  - 同一 key 重复请求幂等，不重复扣库存
  - 扣减商品库存
- `POST /orders/<id>/ship` → 发货（paid → shipped）
- `POST /orders/<id>/deliver` → 送达（shipped → delivered）
- `POST /orders/<id>/cancel` → 取消（pending/paid → cancelled）
  - paid 状态取消时回滚库存
- 非法状态跳转返回 409 Conflict

### 接口返回格式

```json
{"status": "ok", "data": ...}
{"status": "error", "message": "错误描述"}
```

## 验收标准

1. ✅ 所有上述 API 接口可正常调用
2. ✅ `tests/test_basic.py` 中的所有测试用例通过

## 测试

```bash
cd starter && pip install -r requirements.txt && cd .. && python -m pytest tests/ -v
```
