# 最终交付总结 — T2-1 小型博客系统

## 1. 实现功能列表

### 1.1 标签 CRUD（routes_tag.py）

| 接口 | 方法 | 功能 | 状态码 |
|------|------|------|--------|
| `/tags` | POST | 创建标签（name 必填、唯一、非空） | 201 |
| `/tags` | GET | 获取所有标签列表 | 200 |
| `/tags/<id>` | PUT | 编辑标签名称（排除自身唯一性检查） | 200 |
| `/tags/<id>` | DELETE | 删除标签（级联删除文章关联） | 200 |

### 1.2 文章 CRUD + 标签绑定（routes_article.py）

| 接口 | 方法 | 功能 | 状态码 |
|------|------|------|--------|
| `/articles` | POST | 创建文章（title/body 必填） | 201 |
| `/articles` | GET | 列出所有文章（支持 `?tag=` 和 `?tag_id=` 筛选） | 200 |
| `/articles/<id>` | GET | 获取单篇文章 | 200 |
| `/articles/<id>/tags` | POST | 绑定标签到文章 | 200 |
| `/articles/<id>/tags` | GET | 获取文章的所有标签 | 200 |
| `/articles/<id>/tags/<tag_id>` | DELETE | 解除文章与标签的关联（幂等） | 200 |

## 2. 测试覆盖情况

| 测试类 | 测试数 | 通过 | 覆盖范围 |
|--------|--------|------|----------|
| TestArticleCRUD | 4 | 4 | 文章创建、列表、详情、字段验证 |
| TestTagCRUD | 6 | 6 | 标签创建、重复检查、空名称、列表、编辑、删除 |
| TestArticleTagBinding | 4 | 4 | 绑定标签、获取标签、解绑、级联删除 |
| TestFilterArticlesByTag | 4 | 4 | 按名称筛选、按 ID 筛选、无匹配、无筛选参数 |
| **合计** | **18** | **18** | **全部功能点覆盖** |

**测试通过率：100% (18/18)**

## 3. 修改的文件

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `starter/routes_tag.py` | 新增实现 | 标签 CRUD 4 个路由 |
| `starter/routes_article.py` | 新增实现 | 文章路由 6 个 |
| `starter/app.py` | 未修改 | 按约束保持不变 |
| `starter/models.py` | 未修改 | 已有完整实现 |
| `README.md` | 未修改 | 按验收标准保持不变 |

## 4. 项目文档

| 文档 | 说明 |
|------|------|
| `requirements.md` | 需求分析文档（含 11 条隐含需求提取） |
| `design.md` | 方案设计文档（含 API 端点、数据模型、算法、错误处理） |
| `test-report.md` | 测试验证报告（18/18 通过，AC-1 至 AC-4 全部满足） |
| `delivery-summary.md` | 本文档 |

## 5. 已知问题 / 技术债务

1. **SQLAlchemy LegacyAPIWarning**: 代码中 `Query.get()` 在 SQLAlchemy 2.0 中已标记为废弃 API（`Tag.query.get(id)`, `Article.query.get(id)`），建议迁移到 `db.session.get(Model, id)`。功能完全正确，不影响测试结果。

## 6. 验收标准达成情况

| 验收标准 | 结果 |
|----------|------|
| AC-1: 所有 API 接口可正常调用 | ✅ 通过（12 个接口全部可用） |
| AC-2: `tests/test_basic.py` 所有测试用例通过 | ✅ 通过（18/18） |
| AC-3: 错误处理完备（400/404/409/级联） | ✅ 通过 |
| AC-4: README.md 无需修改 | ✅ 通过 |

## 7. 瀑布流程回顾

| 阶段 | ATU | Reviewer 审批次数 | 状态 |
|------|-----|-------------------|------|
| 需求分析 | ATU-001 | 2 次（第一次退回 5 项） | Done |
| 方案设计 | ATU-002 | 2 次（第一次退回 4 项） | Done |
| 开发实现 | ATU-003 | 1 次（直接通过） | Done |
| 开发实现 | ATU-004 | 1 次（直接通过） | Done |
| 测试验证 | ATU-005 | 1 次（直接通过） | Done |
| 最终交付 | ATU-006 | — | Done |
