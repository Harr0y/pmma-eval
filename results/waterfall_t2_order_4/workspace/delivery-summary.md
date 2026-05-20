# 交付总结 — T2-2 订单系统

## 项目概述

本项目实现了一个基于 Flask 的多模块订单系统，包含商品管理、订单 CRUD、订单状态机、支付幂等性和库存管理功能。采用瀑布式项目管理方法，经过 5 个阶段严格推进。

## 实现功能列表

### 商品管理（routes_product.py）
| 端点 | 方法 | 功能 | 状态 |
|------|------|------|------|
| /products | POST | 创建商品（含输入校验、类型转换） | ✅ |
| /products | GET | 列出所有商品 | ✅ |
| /products/\<id\> | GET | 获取商品详情（404 处理） | ✅ |

### 订单管理（routes_order.py）
| 端点 | 方法 | 功能 | 状态 |
|------|------|------|------|
| /orders | POST | 创建订单（库存校验、同商品合并、总价计算） | ✅ |
| /orders/\<id\> | GET | 获取订单详情（含 items） | ✅ |
| /orders | GET | 筛选订单（user_id/status，不含 items） | ✅ |
| /orders/\<id\>/pay | POST | 支付（幂等性、库存扣减） | ✅ |
| /orders/\<id\>/ship | POST | 发货（paid → shipped） | ✅ |
| /orders/\<id\>/deliver | POST | 送达（shipped → delivered） | ✅ |
| /orders/\<id\>/cancel | POST | 取消（pending/paid → cancelled，库存回滚） | ✅ |

### 核心业务逻辑
- **状态机**: 5 个状态（pending/paid/shipped/delivered/cancelled），5 条合法跳转，VALID_TRANSITIONS 映射表统一验证
- **幂等性**: 通过 PaymentRequest 表 + UNIQUE idempotency_key 约束实现
- **库存管理**: 支付时扣减，取消已付款订单时回滚，创建订单时不扣减
- **输入校验**: 必填字段、类型转换、库存不足、商品不存在、空 items

## 修改文件清单

| 文件 | 操作 | 行数 | 说明 |
|------|------|------|------|
| starter/routes_product.py | 重写 | ~60 | 商品 CRUD 路由实现 |
| starter/routes_order.py | 重写 | ~430 | 订单 CRUD + 支付 + 状态机实现 |
| starter/models.py | 未修改 | - | 数据模型（已提供） |
| starter/app.py | 未修改 | - | Flask 应用工厂（已提供） |

## 测试覆盖

| 测试类 | 测试数 | 结果 | 覆盖范围 |
|--------|--------|------|---------|
| TestProductCRUD | 3 | 3/3 PASS | 商品创建、列表、详情 |
| TestOrderCRUD | 4 | 4/4 PASS | 订单创建、库存不足、总价计算、筛选 |
| TestStateMachine | 6 | 6/6 PASS | 支付、发货、送达、3 个非法跳转 |
| TestInventory | 3 | 3/3 PASS | 付款扣库存、取消回滚、pending 不影响 |
| TestIdempotency | 3 | 3/3 PASS | 重复 key、不同 key、缺少 key |
| **总计** | **19** | **19/19 PASS** | |

## 验收标准达成

| # | 验收标准 | 状态 |
|---|---------|------|
| 1 | 商品 API 接口可正常调用 | ✅ |
| 2 | 订单 API 接口可正常调用 | ✅ |
| 3 | 状态机合法跳转，非法返回 409 | ✅ |
| 4 | 库存扣减/回滚正确 | ✅ |
| 5 | 幂等性：重复 key 不重复扣库存 | ✅ |
| 6 | 不同 key 返回 409 | ✅ |
| 7 | 缺少 key 返回 400 | ✅ |
| 8 | 19 个测试全部通过 | ✅ |

## 瀑布阶段回顾

| 阶段 | ATU | Reviewer 审批 | 备注 |
|------|-----|-------------|------|
| 1. 需求分析 | ATU-001 | 第二轮通过 | 测试计数修正、幂等语义明确化 |
| 2. 方案设计 | ATU-002 | 第一轮通过 | |
| 3. 开发实现 | ATU-003~006 | 全部第一轮通过 | 4 个开发 ATU 均一次通过审查 |
| 4. 测试验证 | ATU-007 | 第一轮通过 | 19/19 PASSED |
| 5. 最终交付 | ATU-008 | 待验收 | |

## 已知问题与改进建议

| 优先级 | 问题 | 建议 |
|--------|------|------|
| 低 | SQLAlchemy `Query.get()` 已废弃 | 迁移至 `db.session.get(Model, id)` |
| 低 | `datetime.utcnow()` 已弃用（Python 3.12+） | 迁移至 `datetime.now(datetime.UTC)` |
| 低 | 会话存储为内存模式，重启丢失 | 可引入 Redis/文件持久化 |
| 低 | 无分页支持 | 订单列表可增加分页参数 |

## 交付结论

**项目已完成，所有 8 项验收标准全部通过，19 个测试用例全部通过。符合交付条件。**
