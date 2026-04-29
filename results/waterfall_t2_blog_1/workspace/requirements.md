# 需求分析文档 — T2-1 小型博客系统

## 1. 项目概述

实现一个基于 Flask 的小型博客系统，支持文章管理、标签 CRUD、文章与标签的多对多关联绑定，以及按标签筛选文章。

### 约束条件
- **app.py 不可修改**：Flask 应用工厂和数据库初始化已固定
- **多模块架构**：代码分布在 models.py、routes_article.py、routes_tag.py 三个文件中
- **模块间 import 依赖**：routes_article.py 和 routes_tag.py 需从 models.py 导入模型
- **接口一致性**：各模块之间的模型字段名、关联表名必须保持一致

---

## 2. 功能需求

### 2.1 数据模型需求（models.py）

| 模型 | 字段 | 约束 |
|------|------|------|
| Article | id | Integer, Primary Key |
| Article | title | String(200), NOT NULL |
| Article | body | Text, NOT NULL |
| Article | tags | 与 Tag 的多对多关系（通过 article_tags） |
| Tag | id | Integer, Primary Key |
| Tag | name | String(80), UNIQUE, NOT NULL |
| Tag | articles | 与 Article 的多对多关系（通过 article_tags） |
| article_tags | article_id | Integer, FK → article.id, PK |
| article_tags | tag_id | Integer, FK → tag.id, PK |

**注意**：models.py 当前已有基本定义，需确认是否完整满足需求。

### 2.2 标签 CRUD 路由需求（routes_tag.py）

| 端点 | 方法 | 描述 |
|------|------|------|
| `/tags` | POST | 创建标签 |
| `/tags` | GET | 获取所有标签列表 |
| `/tags/<id>` | PUT | 编辑标签名称 |
| `/tags/<id>` | DELETE | 删除标签 |

#### 2.2.1 POST /tags — 创建标签
- **请求体**：`{"name": "string"}`（name 必填）
- **成功响应**（201）：`{"status": "ok", "data": {"id": int, "name": str}}`
- **错误响应**：
  - 400：name 缺失或为空
  - 409：name 已存在（唯一约束冲突）

#### 2.2.2 GET /tags — 获取标签列表
- **成功响应**（200）：`{"status": "ok", "data": [{"id": int, "name": str}, ...]}`

#### 2.2.3 PUT /tags/<id> — 编辑标签名称
- **请求体**：`{"name": "string"}`（name 必填）
- **成功响应**（200）：`{"status": "ok", "data": {"id": int, "name": str}}`
- **错误响应**：
  - 400：name 缺失
  - 404：标签不存在
  - 409：新 name 与已有标签重名

#### 2.2.4 DELETE /tags/<id> — 删除标签
- **行为**：删除标签，同时级联删除 article_tags 中的所有关联记录
- **成功响应**（200）：`{"status": "ok", "data": {"message": "Tag deleted"}}`
- **错误响应**：404 标签不存在

### 2.3 文章路由需求（routes_article.py）

| 端点 | 方法 | 描述 |
|------|------|------|
| `/articles` | GET | 列出所有文章（支持标签筛选） |
| `/articles` | POST | 创建文章 |
| `/articles/<id>` | GET | 获取单篇文章 |
| `/articles/<id>/tags` | POST | 为文章绑定标签 |
| `/articles/<id>/tags` | GET | 获取文章的所有标签 |
| `/articles/<id>/tags/<tag_id>` | DELETE | 解除文章与标签的关联 |

#### 2.3.1 GET /articles — 列出文章
- **查询参数**（可选）：
  - `?tag=<name>`：按标签名称筛选
  - `?tag_id=<id>`：按标签 ID 筛选
- **成功响应**（200）：`{"status": "ok", "data": [{"id": int, "title": str, "body": str}, ...]}`
- **行为**：不传筛选参数时返回所有文章；按标签筛选无匹配时返回空列表

#### 2.3.2 POST /articles — 创建文章
- **请求体**：`{"title": "string", "body": "string"}`（title 和 body 均必填）
- **成功响应**（201）：`{"status": "ok", "data": {"id": int, "title": str, "body": str}}`
- **错误响应**：400 title 或 body 缺失

#### 2.3.3 GET /articles/<id> — 获取单篇文章
- **成功响应**（200）：`{"status": "ok", "data": {"id": int, "title": str, "body": str}}`
- **错误响应**：404 文章不存在

#### 2.3.4 POST /articles/<id>/tags — 绑定标签
- **请求体**：`{"tag_ids": [int, ...]}`
- **成功响应**（200）：`{"status": "ok", "data": {"message": "Tags bound"}}`
- **错误响应**：
  - 404：文章不存在
  - 400：某个 tag_id 对应的标签不存在

#### 2.3.5 GET /articles/<id>/tags — 获取文章标签
- **成功响应**（200）：`{"status": "ok", "data": [{"id": int, "name": str}, ...]}`
- **错误响应**：404 文章不存在

#### 2.3.6 DELETE /articles/<id>/tags/<tag_id> — 解除关联
- **成功响应**（200）：`{"status": "ok", "data": {"message": "Tag unbound"}}`
- **错误响应**：404 文章不存在

---

## 3. 统一响应格式

| 状态 | 格式 |
|------|------|
| 成功 | `{"status": "ok", "data": ...}` |
| 错误 | `{"status": "error", "message": "错误描述"}` |

---

## 4. 验收标准

| # | 验收项 | 对应测试 |
|---|--------|----------|
| AC-1 | 所有 10 个 API 端点可正常调用 | 手动验证 |
| AC-2 | `test_create_article` — 创建文章成功，返回 201 | TestArticleCRUD |
| AC-3 | `test_list_articles` — 列出所有文章 | TestArticleCRUD |
| AC-4 | `test_get_article` — 获取单篇文章成功 | TestArticleCRUD |
| AC-5 | `test_create_article_missing_fields` — 缺少字段返回 400 | TestArticleCRUD |
| AC-6 | `test_create_tag` — 创建标签成功，返回 201 | TestTagCRUD |
| AC-7 | `test_create_tag_duplicate` — 重复标签返回 409 | TestTagCRUD |
| AC-8 | `test_create_tag_no_name` — name 为空返回 400 | TestTagCRUD |
| AC-9 | `test_list_tags` — 获取标签列表成功 | TestTagCRUD |
| AC-10 | `test_update_tag` — 编辑标签名称成功 | TestTagCRUD |
| AC-11 | `test_delete_tag` — 删除标签成功 | TestTagCRUD |
| AC-12 | `test_bind_tags_to_article` — 绑定标签成功 | TestArticleTagBinding |
| AC-13 | `test_get_article_tags` — 获取文章标签成功 | TestArticleTagBinding |
| AC-14 | `test_unbind_tag_from_article` — 解除关联成功 | TestArticleTagBinding |
| AC-15 | `test_delete_tag_removes_bindings` — 删除标签时级联解除关联 | TestArticleTagBinding |
| AC-16 | `test_filter_by_tag_name` — 按标签名筛选文章 | TestFilterArticlesByTag |
| AC-17 | `test_filter_by_tag_id` — 按标签 ID 筛选文章 | TestFilterArticlesByTag |
| AC-18 | `test_filter_no_match` — 无匹配返回空列表 | TestFilterArticlesByTag |
| AC-19 | `test_no_filter_returns_all` — 无筛选返回所有文章 | TestFilterArticlesByTag |
| AC-20 | tests/test_basic.py 全部 16 个测试用例通过 | 整体验收 |

---

## 5. 隐含需求与边界条件

| # | 隐含需求 | 来源 |
|---|----------|------|
| IR-1 | models.py 已定义好基本模型，需确认无需修改 | app.py import 路径 |
| IR-2 | routes_tag.py 和 routes_article.py 需从 models.py 导入 db 和模型 | 跨模块依赖 |
| IR-3 | Blueprint 名称必须为 `article_bp` 和 `tag_bp` | app.py 注册 |
| IR-4 | 删除标签时需级联删除 article_tags 关联记录 | test_delete_tag_removes_bindings |
| IR-5 | GET /articles 的筛选参数为可选，不传时返回全部 | test_no_filter_returns_all |
| IR-6 | 筛选无匹配时返回空列表而非 404 | test_filter_no_match |
| IR-7 | POST /articles/<id>/tags 需处理不存在的 tag_id | routes_article.py 注释 |
| IR-8 | POST /tags 创建时需处理空字符串 name（不仅是缺失） | test_create_tag_no_name |
