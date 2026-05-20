# 需求分析文档 — T2-1 小型博客系统

## 1. 项目概述

实现一个基于 Flask 的小型博客系统，支持文章管理、标签 CRUD、文章与标签的多对多绑定，以及按标签筛选文章。代码分布在多个模块中，需要保持模块间接口一致。

## 2. 约束条件

- **app.py 不可修改**：Flask 应用工厂和 DB 初始化已固定
- **多模块架构**：routes_article.py 和 routes_tag.py 需要从 models.py 导入模型
- **Blueprint 注册**：app.py 已完成 Blueprint 注册，路由文件必须定义正确的 Blueprint 实例
- **Blueprint 无 url_prefix**：app.py 中 `app.register_blueprint(article_bp)` 和 `app.register_blueprint(tag_bp)` 均未指定 url_prefix，因此路由文件中的端点路径必须与 README.md 中列出的完全一致（直接以 `/articles`、`/tags` 开头）
- **数据模型现状**：README.md 将 models.py 标记为"需要完善"，但经审查 models.py 中 Article、Tag、article_tags 的定义已包含所有必要字段（id, title, body, name, 多对多关联），当前模型定义完整。开发者需理解模型结构并确保路由实现与之一致，但无需修改 models.py

## 3. 功能需求

### 3.1 数据模型（已实现，开发者需理解其结构）

- **Article**：id (PK), title (String 200, non-null), body (Text, non-null), tags (多对多关系)
- **Tag**：id (PK), name (String 80, unique, non-null), articles (反向多对多关系)
- **article_tags**：多对多关联表 (article_id, tag_id, 联合主键)

**ORM 隐含需求**：测试文件 test_basic.py 中的 `sample_article` fixture 直接通过 SQLAlchemy ORM 操作数据库（`db.session.add()` / `db.session.commit()`）创建文章，而非通过 API 调用。因此 Article/Tag 模型必须支持标准构造函数初始化（如 `Article(title='...', body='...')`），且 `id` 字段须在 commit 后自动生成。

### 3.2 文章路由（routes_article.py）

#### FR-ART-01: 创建文章
- **端点**：`POST /articles`
- **请求体**：`{"title": "str", "body": "str"}`
- **成功响应** (201)：`{"status": "ok", "data": {"id": int, "title": str, "body": str}}`
- **错误响应** (400)：title 或 body 缺失时返回 `{"status": "error", "message": "..."}`

#### FR-ART-02: 列出所有文章
- **端点**：`GET /articles`
- **查询参数（可选）**：
  - `tag=<name>` — 按标签名称筛选
  - `tag_id=<id>` — 按标签 ID 筛选
- **成功响应** (200)：`{"status": "ok", "data": [{"id": int, "title": str, "body": str}, ...]}`
- **无匹配时**：返回空列表 `[]`

#### FR-ART-03: 获取单篇文章
- **端点**：`GET /articles/<id>`
- **成功响应** (200)：`{"status": "ok", "data": {"id": int, "title": str, "body": str}}`
- **错误响应** (404)：文章不存在时

#### FR-ART-04: 为文章绑定标签
- **端点**：`POST /articles/<id>/tags`
- **请求体**：`{"tag_ids": [int, ...]}`
- **成功响应** (200)：`{"status": "ok", "data": {"message": "Tags bound"}}`
- **错误响应**：
  - 404：文章不存在
  - 400：tag_ids 中有不存在的标签 ID

#### FR-ART-05: 获取文章的所有标签
- **端点**：`GET /articles/<id>/tags`
- **成功响应** (200)：`{"status": "ok", "data": [{"id": int, "name": str}, ...]}`
- **错误响应** (404)：文章不存在时

#### FR-ART-06: 解除文章与标签的关联
- **端点**：`DELETE /articles/<id>/tags/<tag_id>`
- **成功响应** (200)：`{"status": "ok", "data": {"message": "Tag unbound"}}`
- **错误响应** (404)：文章不存在时

### 3.3 标签路由（routes_tag.py）

#### FR-TAG-01: 创建标签
- **端点**：`POST /tags`
- **请求体**：`{"name": "str"}`
- **成功响应** (201)：`{"status": "ok", "data": {"id": int, "name": str}}`
- **错误响应**：
  - 400：name 缺失或为空
  - 409：name 已存在（重复）

#### FR-TAG-02: 获取所有标签
- **端点**：`GET /tags`
- **成功响应** (200)：`{"status": "ok", "data": [{"id": int, "name": str}, ...]}`

#### FR-TAG-03: 编辑标签名称
- **端点**：`PUT /tags/<id>`
- **请求体**：`{"name": "str"}`
- **成功响应** (200)：`{"status": "ok", "data": {"id": int, "name": str}}`
- **错误响应**：
  - 404：标签不存在
  - 400：name 缺失
  - 409：name 与已有标签重复

#### FR-TAG-04: 删除标签
- **端点**：`DELETE /tags/<id>`
- **成功响应** (200)：`{"status": "ok", "data": {"message": "Tag deleted"}}`
- **错误响应** (404)：标签不存在时
- **级联行为**：删除标签时必须同时解除与所有文章的关联（article_tags 表中的记录）

## 4. 接口返回格式规范

- **成功**：`{"status": "ok", "data": ...}`
- **错误**：`{"status": "error", "message": "错误描述"}`

## 5. 验收标准

1. 所有上述 10 个 API 接口可正常调用，返回格式和状态码符合规范
2. `tests/test_basic.py` 中所有 18 个测试用例全部通过：
   - TestArticleCRUD: 4 个（创建、列表、获取、缺少字段）
   - TestTagCRUD: 6 个（创建、重复、无名称、列表、编辑、删除）
   - TestArticleTagBinding: 4 个（绑定、获取、解绑、级联删除）
   - TestFilterArticlesByTag: 4 个（按名称筛选、按 ID 筛选、无匹配、全部返回）
3. README.md 无需修改

**注**：`test_no_filter_returns_all` 是唯一一个未显式断言状态码的测试用例（仅断言数据长度），但实现时仍需确保 GET /articles 返回 200。

## 6. 隐含需求与边界条件

- **绑定标签幂等性**：多次绑定同一标签不应产生重复记录（多对多表有联合主键保护）
- **解绑不存在的关联**：DELETE /articles/<id>/tags/<tag_id> 中，即使该标签未绑定到该文章，也应返回成功（注：此边界条件无对应测试覆盖，属于额外需求，需手动验证）
- **标签筛选优先级**：同时传递 tag 和 tag_id 参数时的行为未在测试中覆盖，可任选其一或合并
- **并发安全**：SQLite 在单线程模式下运行，无需考虑并发问题
- **空数据库状态**：GET /articles 和 GET /tags 在空数据库时应返回空列表
