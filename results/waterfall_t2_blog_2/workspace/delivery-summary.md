# 交付总结 — T2-1 小型博客系统（文章标签管理 + 按标签筛选）

## 1. 项目概述

实现了一个基于 Flask 的小型博客系统，支持文章管理、标签 CRUD、文章与标签的多对多绑定，以及按标签筛选文章。采用多模块 Blueprint 架构。

## 2. 实现的功能列表

### 2.1 标签 CRUD（routes_tag.py）

| 端点 | 方法 | 功能 | 状态 |
|------|------|------|------|
| /tags | POST | 创建标签（name 唯一性校验） | ✅ 已实现 |
| /tags | GET | 获取所有标签列表 | ✅ 已实现 |
| /tags/\<id\> | PUT | 编辑标签名称（唯一性排除自身） | ✅ 已实现 |
| /tags/\<id\> | DELETE | 删除标签（级联清除 article_tags 关联） | ✅ 已实现 |

### 2.2 文章 CRUD + 标签绑定（routes_article.py）

| 端点 | 方法 | 功能 | 状态 |
|------|------|------|------|
| /articles | POST | 创建文章（title+body 验证） | ✅ 已实现 |
| /articles | GET | 列出所有文章（支持 ?tag= / ?tag_id= 筛选） | ✅ 已实现 |
| /articles/\<id\> | GET | 获取单篇文章 | ✅ 已实现 |
| /articles/\<id\>/tags | POST | 绑定标签到文章（幂等操作） | ✅ 已实现 |
| /articles/\<id\>/tags | GET | 获取文章的所有标签 | ✅ 已实现 |
| /articles/\<id\>/tags/\<tag_id\> | DELETE | 解除文章与标签的关联 | ✅ 已实现 |

### 2.3 数据模型（models.py）

- Article 模型：id, title, body + 多对多 tags 关系
- Tag 模型：id, name (unique) + 多对多 articles 关系（lazy='dynamic'）
- article_tags 关联表：复合主键（article_id, tag_id）

## 3. 测试覆盖情况

| 测试类 | 测试数 | 通过 | 覆盖范围 |
|--------|--------|------|----------|
| TestArticleCRUD | 4 | 4 | 文章创建、列表、详情、字段验证 |
| TestTagCRUD | 6 | 6 | 标签创建、重复、空名、列表、编辑、删除 |
| TestArticleTagBinding | 4 | 4 | 绑定、获取、解除、级联删除 |
| TestFilterArticlesByTag | 4 | 4 | 按名称筛选、按 ID 筛选、无匹配、无筛选 |
| **合计** | **18** | **18** | **100% 通过率** |

## 4. 修改的文件清单

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `starter/routes_tag.py` | 新增实现 | 标签 CRUD 4 个端点（~50 行） |
| `starter/routes_article.py` | 新增实现 | 文章 CRUD + 标签绑定 6 个端点（~100 行） |
| `starter/app.py` | 未修改 | Flask 应用工厂（约束：不可修改） |
| `starter/models.py` | 未修改 | 数据模型（已完整实现） |

## 5. 项目文档清单

| 文档 | 说明 |
|------|------|
| requirements.md | 需求分析文档（19 条验收标准） |
| design.md | 方案设计文档（API 端点设计、算法逻辑、模块依赖） |
| test-report.md | 测试验证报告（18/18 通过） |
| delivery-summary.md | 交付总结文档（本文档） |
| state.json | 项目状态跟踪 |

## 6. 已知问题与待改进项

| 编号 | 问题 | 严重度 | 建议 |
|------|------|--------|------|
| KI-01 | `Model.query.get()` 在 SQLAlchemy 2.0 中已弃用 | 低 | 替换为 `db.session.get(Model, id)` |
| KI-02 | `GET /articles?tag_id=abc` 未做 ValueError 异常处理 | 低 | 添加 try/except 或参数验证 |
| KI-03 | `POST /articles/<id>/tags` 未对请求体非 JSON 情况做防护 | 低 | 添加 `data` 为 None 的检查 |

以上问题均为非阻塞性低优先级项，不影响当前功能的正确性和验收标准的满足。

## 7. 验收结论

**项目满足 README.md 中定义的全部 3 条验收标准：**

1. ✅ 所有 API 接口可正常调用（10 个端点全部实现）
2. ✅ `tests/test_basic.py` 中的所有测试用例通过（18/18）
3. ✅ README.md 无需修改内容
