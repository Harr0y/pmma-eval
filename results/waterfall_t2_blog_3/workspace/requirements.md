# 需求分析文档 — T2-1 小型博客系统

## 1. 项目概述

实现一个基于 Flask 的小型博客系统，核心功能为**文章管理**、**标签 CRUD**、**文章-标签绑定/解绑**，以及**按标签筛选文章**。项目采用多模块架构，代码分布在 `models.py`、`routes_article.py`、`routes_tag.py` 三个文件中。

## 2. 功能需求

### 2.1 数据模型 (models.py)

| 模型 | 字段 | 约束 |
|------|------|------|
| **Article** | id (Integer) | 主键，自增 |
| | title (String) | 非空，最大长度 200 |
| | body (Text) | 非空 |
| **Tag** | id (Integer) | 主键，自增 |
| | name (String) | 非空，唯一，最大长度 80 |
| **article_tags** | article_id (Integer) | 外键 → article.id，联合主键 |
| | tag_id (Integer) | 外键 → tag.id，联合主键 |

- Article 与 Tag 为多对多关系，通过 `article_tags` 关联表实现
- Article 需要能通过 `tags` 属性访问关联的 Tag 列表
- Tag 需要能通过 `articles` 属性访问关联的 Article 列表

### 2.2 文章路由 (routes_article.py)

使用 Blueprint `article_bp` 注册，提供以下接口：

#### GET /articles
- 功能：列出所有文章，支持按标签筛选
- 查询参数（可选）：
  - `tag` — 按标签名称筛选
  - `tag_id` — 按标签 ID 筛选
- 成功响应 (200)：`{"status": "ok", "data": [{"id": int, "title": str, "body": str}, ...]}`
- 无匹配时返回空列表，仍为 200

#### POST /articles
- 功能：创建文章
- 请求体：`{"title": str, "body": str}`
- 成功响应 (201)：`{"status": "ok", "data": {"id": int, "title": str, "body": str}}`
- 错误响应 (400)：缺少 title 或 body 字段

#### GET /articles/<id>
- 功能：获取单篇文章详情
- 成功响应 (200)：`{"status": "ok", "data": {"id": int, "title": str, "body": str}}`
- 错误响应 (404)：文章不存在

#### POST /articles/<id>/tags
- 功能：为文章绑定一个或多个标签
- 请求体：`{"tag_ids": [int, ...]}`
- 成功响应 (200)：`{"status": "ok", "data": {"message": "Tags bound"}}`
- **幂等性**：重复绑定同一标签为幂等操作，不会报错，直接返回 200
- 错误响应：
  - (404)：文章不存在
  - (400)：指定的 tag_id 对应的标签不存在

#### GET /articles/<id>/tags
- 功能：获取文章的所有标签
- 成功响应 (200)：`{"status": "ok", "data": [{"id": int, "name": str}, ...]}`
- 错误响应 (404)：文章不存在

#### DELETE /articles/<id>/tags/<tag_id>
- 功能：解除文章与标签的关联
- 成功响应 (200)：`{"status": "ok", "data": {"message": "Tag unbound"}}`
- **幂等性**：解绑一个未绑定的标签为幂等操作，不会报错，直接返回 200
- 错误响应 (404)：文章不存在

### 2.3 标签路由 (routes_tag.py)

使用 Blueprint `tag_bp` 注册，提供以下接口：

#### POST /tags
- 功能：创建标签
- 请求体：`{"name": str}`
- 成功响应 (201)：`{"status": "ok", "data": {"id": int, "name": str}}`
- 错误响应：
  - (400)：name 缺失或为空
  - (409)：标签名称已存在

#### GET /tags
- 功能：获取所有标签列表
- 成功响应 (200)：`{"status": "ok", "data": [{"id": int, "name": str}, ...]}`

#### PUT /tags/<id>
- 功能：编辑标签名称
- 请求体：`{"name": str}`
- 成功响应 (200)：`{"status": "ok", "data": {"id": int, "name": str}}`
- 错误响应：
  - (404)：标签不存在
  - (400)：name 缺失
  - (409)：新名称与其他标签重复

#### DELETE /tags/<id>
- 功能：删除标签，同时级联删除 article_tags 中的关联记录
- 成功响应 (200)：`{"status": "ok", "data": {"message": "Tag deleted"}}`
- 错误响应 (404)：标签不存在

## 3. 统一响应格式

所有接口遵循统一格式：

- **成功**：`{"status": "ok", "data": ...}`
- **错误**：`{"status": "error", "message": "错误描述"}`

## 4. 非功能需求

- **多模块一致性**：`routes_article.py` 和 `routes_tag.py` 引用的模型字段名、关联表名必须与 `models.py` 保持一致
- **不修改 app.py**：应用工厂和 DB 初始化代码不可修改
- **测试框架**：使用 pytest，测试文件位于 `tests/test_basic.py`

## 5. 验收标准

| # | 验收项 | 对应测试 |
|---|--------|---------|
| AC-1 | POST /articles 创建文章，返回 201 和正确数据 | TestArticleCRUD::test_create_article |
| AC-2 | GET /articles 列出所有文章 | TestArticleCRUD::test_list_articles |
| AC-3 | GET /articles/<id> 获取单篇文章 | TestArticleCRUD::test_get_article |
| AC-4 | POST /articles 缺少字段返回 400 | TestArticleCRUD::test_create_article_missing_fields |
| AC-5 | POST /tags 创建标签，返回 201 | TestTagCRUD::test_create_tag |
| AC-6 | POST /tags 重复名称返回 409 | TestTagCRUD::test_create_tag_duplicate |
| AC-7 | POST /tags 无 name 返回 400 | TestTagCRUD::test_create_tag_no_name |
| AC-8 | GET /tags 列出所有标签 | TestTagCRUD::test_list_tags |
| AC-9 | PUT /tags/<id> 编辑标签名称 | TestTagCRUD::test_update_tag |
| AC-10 | DELETE /tags/<id> 删除标签 | TestTagCRUD::test_delete_tag |
| AC-11 | POST /articles/<id>/tags 绑定标签 | TestArticleTagBinding::test_bind_tags_to_article |
| AC-12 | GET /articles/<id>/tags 获取文章标签 | TestArticleTagBinding::test_get_article_tags |
| AC-13 | DELETE /articles/<id>/tags/<tag_id> 解绑 | TestArticleTagBinding::test_unbind_tag_from_article |
| AC-14 | 删除标签时级联解除关联 | TestArticleTagBinding::test_delete_tag_removes_bindings |
| AC-15 | GET /articles?tag=name 按标签名筛选 | TestFilterArticlesByTag::test_filter_by_tag_name |
| AC-16 | GET /articles?tag_id=id 按标签 ID 筛选 | TestFilterArticlesByTag::test_filter_by_tag_id |
| AC-17 | 筛选无匹配返回空列表 | TestFilterArticlesByTag::test_filter_no_match |
| AC-18 | 不传筛选参数返回所有文章 | TestFilterArticlesByTag::test_no_filter_returns_all |

## 6. 约束与限制

- SQLite 数据库（开发和测试环境）
- Flask >= 3.0 + Flask-SQLAlchemy >= 3.1
- 无需用户认证/授权
- 无需分页
- 无需前端
