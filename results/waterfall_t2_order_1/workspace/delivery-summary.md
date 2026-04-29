# T2-2 最终交付报告

## 1. 项目概述

**任务**：T2-2 订单系统 — 订单状态机 + 库存扣减（多模块版本）
**方法论**：Waterfall（瀑布式项目管理）
**状态**：已完成 ✅

## 2. 实现的功能

### 2.1 商品管理（routes_product.py）
| 接口 | 方法 | 描述 |
|------|------|------|
| /products | GET | 列出所有商品 |
| /products | POST | 创建商品（含输入验证） |
| /products/\<id\> | GET | 获取商品详情（含 404 处理） |

### 2.2 订单管理（routes_order.py）
| 接口 | 方法 | 描述 |
|------|------|------|
| /orders | POST | 创建订单（库存校验、总价计算） |
| /orders/\<id\> | GET | 订单详情（含 items 列表） |
| /orders | GET | 订单筛选（user_id、status） |
| /orders/\<id\>/pay | POST | 幂等支付（idempotency_key+order_id 联合查询、库存扣减） |
| /orders/\<id\>/ship | POST | 发货（状态机校验） |
| /orders/\<id\>/deliver | POST | 送达（状态机校验） |
| /orders/\<id\>/cancel | POST | 取消（paid 状态回滚库存） |

### 2.3 核心业务逻辑
- **状态机**：pending → paid → shipped → delivered，pending/paid → cancelled
- **幂等支付**：通过 Idempotency-Key header + PaymentRequest 记录实现
- **库存管理**：支付时扣减，取消已支付订单时回滚，创建时不扣减

## 3. 测试覆盖

| 指标 | 结果 |
|------|------|
| 测试用例总数 | 19 |
| 通过 | 19 |
| 失败 | 0 |
| 通过率 | 100% |
| 验收标准 | 7/7 PASS |

**测试分类覆盖**：
- 商品 CRUD：3 个测试
- 订单 CRUD：4 个测试
- 状态机（合法+非法转换）：6 个测试
- 库存管理：3 个测试
- 幂等性：3 个测试

## 4. 修改的文件

| 文件 | 操作 | 说明 |
|------|------|------|
| starter/routes_product.py | 重写 | 实现 3 个商品 API 接口 |
| starter/routes_order.py | 重写 | 实现 7 个订单 API 接口 |
| starter/models.py | 未修改 | 数据模型已完整 |
| starter/app.py | 未修改 | 应用工厂无需修改 |

## 5. 已知问题与改进建议

| 问题 | 优先级 | 说明 |
|------|--------|------|
| `Product.query.get()` LegacyAPIWarning | 低 | routes_product.py 使用 SQLAlchemy 1.x API，建议改为 `db.session.get()` |
| `datetime.utcnow()` 弃用 | 低 | Python 3.12+ 标记弃用，建议改为 `datetime.now(datetime.UTC)` |
| 测试覆盖盲区 | 建议 | shipped→cancelled、商品不存在创建订单、items 空列表等边界场景无显式测试 |

## 6. 阶段回顾

| 阶段 | ATU | 状态 | Reviewer 轮次 |
|------|-----|------|--------------|
| 需求分析 | ATU-001 | Done | 1 轮通过 |
| 方案设计 | ATU-002 | Done | 2 轮（第1轮退回7项，第2轮通过） |
| 开发实现 | ATU-003 | Done | 1 轮通过 |
| 开发实现 | ATU-004 | Done | 1 轮通过 |
| 测试验证 | ATU-005 | Done | 1 轮通过 |
| 最终交付 | ATU-006 | Done | 待验收 |
