# 交付总结 — T3 微型电商订单系统

## 项目概述

本项目采用**瀑布式项目管理方法（Waterfall）**，实现了基于 Flask + SQLAlchemy 的微型电商订单系统，支持产品管理、订单系统、RBAC 权限控制，以及 change.md 中要求的渠道追溯、限流和原子库存扣减功能。

## 实现的功能列表

### 核心功能

| 功能 | 端点 | 描述 |
|------|------|------|
| 产品列表 | `GET /products` | 返回所有产品，无需认证 |
| 创建产品 | `POST /products` | Admin only，含输入验证 |
| 创建订单 | `POST /orders` | 含限流、原子库存扣减、origin 参数 |
| 查看订单 | `GET /orders` | Admin 看全部，用户看自己的 |

### RBAC 权限控制

- `X-User-Id` Header 认证机制
- Admin 角色可创建产品
- 普通用户仅可查看自己的订单

### 需求变更实现（change.md）

| 变更 | 实现方式 |
|------|----------|
| 订单 origin 字段 | Order 模型新增 `origin` 字段（默认 'web'），支持自定义 |
| 10 秒限流 | `middleware.check_rate_limit()` + `mark_order_placed()` |
| 原子库存扣减 | `UPDATE ... WHERE stock >= quantity` 条件 UPDATE（SQLite 兼容） |

## 修改的文件

| 文件 | 变更内容 | ATU |
|------|----------|-----|
| `starter/models.py` | Order 模型新增 `origin` 字段 | ATU-003 |
| `starter/middleware.py` | 新增限流函数 `check_rate_limit()`, `mark_order_placed()`, `clear_rate_limits()` | ATU-004 |
| `starter/routes_product.py` | 实现 `GET /products` 和 `POST /products` | ATU-005 |
| `starter/routes_order.py` | 实现 `POST /orders` 和 `GET /orders` | ATU-006 |
| `tests/test_basic.py` | 添加 `clear_rate_limits()` 测试隔离 | ATU-006 |
| `tests/test_change.py` | 添加 `clear_rate_limits()` 测试隔离 | ATU-006 |

**未修改的文件**：`app.py`（框架约束）

## 测试覆盖情况

| 指标 | 数值 |
|------|------|
| 测试总数 | 19 |
| 通过数 | 19 |
| 失败数 | 0 |
| 通过率 | 100% |

### 按模块分布

| 模块 | 测试数 | 状态 |
|------|--------|------|
| TestProductManagement | 4 | 全部通过 |
| TestOrderSystem | 7 | 全部通过 |
| TestRBAC | 2 | 全部通过 |
| TestOrderOrigin | 2 | 全部通过 |
| TestRateLimiting | 2 | 全部通过 |
| TestAtomicStock | 2 | 全部通过 |

### 验收标准覆盖

- 22 项验收条目中 19 项有显式测试覆盖
- 3 项依赖实现保证（空列表返回、GET /orders 返回 origin、并发超卖防护）

## 项目管理统计

| 指标 | 数值 |
|------|------|
| 方法 | Waterfall（瀑布式） |
| 阶段数 | 5（需求→设计→开发→测试→交付） |
| ATU 总数 | 8 |
| ATU 完成 | 8/8 |
| Reviewer 审批次数 | 9（需求1次、设计2次、开发3次、测试2次、交付1次） |
| 需求退回次数 | 1（design.md 第一轮因 SQLite FOR UPDATE 问题退回） |
| 测试报告退回次数 | 1（test-report.md 第一轮因验收覆盖标注不准确退回） |

## 已知问题与待改进项

1. **SQLAlchemy LegacyAPIWarning**：`Query.get()` 在 SQLAlchemy 2.0 中已废弃，建议迁移至 `db.session.get()`
2. **origin 参数类型验证**：未显式校验 origin 是否为字符串，依赖数据库层兜底
3. **测试冗余**：TestRBAC 与 TestProductManagement 存在 2 个重复测试用例
4. **并发测试缺失**：无多线程并发下单测试，依赖 SQL 层原子性保证
5. **会话持久化**：当前使用内存存储，重启后丢失（原始设计约束）
6. **限流内存泄漏**：`_rate_limit_store` 无清理机制，长期运行需补充清理逻辑

## 结论

项目按照瀑布式流程完成全部 5 个阶段，所有 8 个 ATU 均已交付。19/19 测试全部通过，系统功能完整，符合 README.md 和 change.md 的需求规格。
