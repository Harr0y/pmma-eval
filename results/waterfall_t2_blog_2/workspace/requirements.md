# 需求分析文档 — T2-1 小型博客系统（文章标签管理 + 按标签筛选）

## 1. 项目概述

实现一个基于 Flask 的小型博客系统，支持文章管理、标签 CRUD、文章与标签的多对多绑定，以及按标签筛选文章。系统采用多模块架构，代码分布在 `models.py`、`routes_article.py`、`routes_tag.py` 三个模块中。

**约束条件**：
- `app.py` 为 Flask 应用工厂，**不可修改**
- `app.py` 第 24 行 `from models import Article, Tag` — `models.py` **必须导出** `Article` 和 `Tag` 两个类
- 各模块之间通过 `models.py` 中的模型定义进行接口对接
- 接口返回格式统一：成功时 `{"status": "ok", "data": ...}`，错误时 `{"status": "error", "message": "..."}`
- 测试文件 `tests/test_basic.py` 不可修改，是验收的唯一标准

## 2. 功能需求

### 2.1 数据模型（models.py）

| 模型 | 字段 | 约束 |
|------|------|------|
| Article | id (Integer, PK) | 自增主键 |
| Article | title (String(200)) | 非空 |
| Article | body (Text) | 非空 |
| Tag | id (Integer, PK) | 自增主键 |
| Tag | name (String(80)) | 唯一、非空 |
| article_tags | article_id (Integer, FK→article.id) | 复合主键之一 |
| article_tags | tag_id (Integer, FK→tag.id) | 复合主键之一 |

**关联关系**：
- Article ↔ Tag：多对多，通过 `article_tags` 关联表
- Article.tags：获取文章的所有标签
- Tag.articles：获取标签下的所有文章（lazy='dynamic'，已由 models.py 实现，无需额外测试）

**现状**：`models.py` 已完整实现，字段定义与上述规格一致。

### 2.2 文章路由（routes_article.py）

Blueprint 名称：`article_bp`

| 端点 | 方法 | 描述 | 请求体 | 成功响应 | 错误码 |
|------|------|------|--------|----------|--------|
| `/articles` | GET | 列出所有文章 | 可选 `?tag=<name>` 或 `?tag_id=<id>` | `{"status":"ok","data":[{"id","title","body"}]}` | — |
| `/articles` | POST | 创建文章 | `{"title":"...","body":"..."}` | `{"status":"ok","data":{"id","title","body"}}` (201) | 400：缺少 title 或 body |
| `/articles/<id>` | GET | 获取单篇文章 | — | `{"status":"ok","data":{"id","title","body"}}` | 404：文章不存在 |
| `/articles/<id>/tags` | POST | 绑定标签到文章 | `{"tag_ids":[1,2]}` | `{"status":"ok","data":{"message":"Tags bound"}}` | 404：文章不存在 |
| `/articles/<id>/tags` | GET | 获取文章的所有标签 | — | `{"status":"ok","data":[{"id","name"}]}` | 404：文章不存在 |
| `/articles/<id>/tags/<tag_id>` | DELETE | 解除文章与标签的关联 | — | `{"status":"ok","data":{"message":"Tag unbound"}}` | 404：文章不存在 |

### 2.3 标签路由（routes_tag.py）

Blueprint 名称：`tag_bp`

| 端点 | 方法 | 描述 | 请求体 | 成功响应 | 错误码 |
|------|------|------|--------|----------|--------|
| `/tags` | POST | 创建标签 | `{"name":"..."}` | `{"status":"ok","data":{"id","name"}}` (201) | 400：name 缺失/空；409：name 已存在 |
| `/tags` | GET | 获取所有标签 | — | `{"status":"ok","data":[{"id","name"}]}` | — |
| `/tags/<id>` | PUT | 编辑标签名称 | `{"name":"..."}` | `{"status":"ok","data":{"id","name"}}` | 404：标签不存在；400：name 缺失；409：name 重复 |
| `/tags/<id>` | DELETE | 删除标签 | — | `{"status":"ok","data":{"message":"Tag deleted"}}` | 404：标签不存在 |

**级联行为**：删除标签时，必须同时删除 `article_tags` 关联表中所有相关记录。

### 2.4 按标签筛选文章

`GET /articles` 支持两种可选的筛选参数：

1. `?tag=<name>` — 按标签名称筛选，返回绑定了该标签的所有文章
2. `?tag_id=<id>` — 按标签 ID 筛选，返回绑定了该标签的所有文章

无匹配结果时返回空列表 `[]`（状态码 200）。
不传筛选参数时返回所有文章。

## 3. 验收标准

> **原则**：验收标准严格对应 `tests/test_basic.py` 中的测试用例。每个 AC 可由对应测试明确验证。

| 编号 | 验收标准 | 对应测试用例 | 验证内容 |
|------|----------|-------------|----------|
| AC-01 | `POST /articles` 正常创建文章 | `test_create_article` | status_code==201, status=='ok', data.title 匹配 |
| AC-02 | `GET /articles` 返回所有文章 | `test_list_articles` | status_code==200, data 长度正确 |
| AC-03 | `GET /articles/<id>` 返回单篇文章 | `test_get_article` | status_code==200, data.title 匹配 |
| AC-04 | 缺少 body 时返回 400 | `test_create_article_missing_fields` | 仅传 title 不传 body → 400 |
| AC-05 | `POST /tags` 创建标签，返回 201 | `test_create_tag` | status_code==201, data.name 匹配 |
| AC-06 | 重复标签名返回 409 | `test_create_tag_duplicate` | 相同 name 创建两次 → 第二次 409 |
| AC-07 | 缺少 name 时返回 400 | `test_create_tag_no_name` | 传空 JSON `{}` → 400 |
| AC-08 | `GET /tags` 返回所有标签 | `test_list_tags` | status_code==200, data 长度正确 |
| AC-09 | `PUT /tags/<id>` 编辑标签名 | `test_update_tag` | status_code==200, data.name 为新值 |
| AC-10 | `DELETE /tags/<id>` 删除标签 | `test_delete_tag` | status_code==200, 删除后列表为空 |
| AC-11 | `POST /articles/<id>/tags` 绑定标签 | `test_bind_tags_to_article` | status_code==200 |
| AC-12 | `GET /articles/<id>/tags` 获取文章标签 | `test_get_article_tags` | status_code==200, data 长度和 name 正确 |
| AC-13 | `DELETE /articles/<id>/tags/<tag_id>` 解除绑定 | `test_unbind_tag_from_article` | status_code==200, 解除后标签列表为空 |
| AC-14 | 删除标签时级联解除关联 | `test_delete_tag_removes_bindings` | 删除标签后文章标签列表为空 |
| AC-15 | `GET /articles?tag=Python` 按标签名筛选 | `test_filter_by_tag_name` | status_code==200, 仅返回匹配文章 |
| AC-16 | `GET /articles?tag_id=<id>` 按标签 ID 筛选 | `test_filter_by_tag_id` | status_code==200, 仅返回匹配文章 |
| AC-17 | 筛选无匹配返回空列表 | `test_filter_no_match` | status_code==200, data 为空列表 |
| AC-18 | 不传筛选参数返回所有文章 | `test_no_filter_returns_all` | 返回所有已创建文章 |
| AC-19 | `tests/test_basic.py` 全部通过 | pytest 运行 | 所有测试 PASS |

## 4. 边界条件与实现指引

> 以下边界条件基于 README.md 的隐含要求，虽无独立测试用例覆盖，但实现时应处理以防影响已有测试。

| 场景 | 预期行为 | 测试覆盖 |
|------|----------|----------|
| 缺少 title 或 body（POST /articles） | 400 | ✅ AC-04 仅覆盖缺少 body |
| name 缺失（POST /tags） | 400 | ✅ AC-07 覆盖 `{}` 请求 |
| 重复标签名（POST /tags） | 409 | ✅ AC-06 覆盖 |
| 对不存在的文章操作 | 404 | ⚠️ 无独立测试，但测试 fixture 始终使用有效 ID |
| 对不存在的标签操作 | 404 | ⚠️ 无独立测试 |
| 删除标签级联删除关联 | 关联自动清除 | ✅ AC-14 覆盖 |
| 重复绑定同一标签 | 幂等操作（不报错） | ⚠️ 无独立测试 |
| 同时传 tag 和 tag_id | 任选其一筛选或返回全部 | ⚠️ 无测试覆盖，非关键 |

> **注意**：标记 ⚠️ 的场景无独立测试覆盖，实现时应遵循合理默认行为但不作为验收门控。

## 5. 技术约束

- Python 3.x + Flask 3.0+ + Flask-SQLAlchemy 3.1+
- 数据库：SQLite（开发环境）
- 测试框架：pytest
- 不修改 `app.py`
- 不修改 `tests/test_basic.py`
- 代码仅限 `starter/` 目录
- `models.py` 必须导出 `Article`、`Tag` 类和 `article_tags` 表（`app.py` 依赖此导入）
