# 方案设计文档 — T2-1 小型博客系统

## 1. 设计概述

本系统采用 Flask + SQLAlchemy 架构，通过多模块 Blueprint 组织路由。数据模型已定义在 models.py 中，开发工作聚焦于实现两个路由模块。

## 2. 数据库设计

### 2.1 已有表结构（models.py，无需修改）

**Article 表**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, auto-increment | 主键 |
| title | String(200) | NOT NULL | 文章标题 |
| body | Text | NOT NULL | 文章内容 |

**Tag 表**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, auto-increment | 主键 |
| name | String(80) | UNIQUE, NOT NULL | 标签名称 |

**article_tags 关联表**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| article_id | Integer | FK(article.id), PK(联合) | 文章 ID |
| tag_id | Integer | FK(tag.id), PK(联合) | 标签 ID |

### 2.2 关系说明

- Article ↔ Tag：多对多关系，通过 article_tags 表关联
- Article.tags：获取文章的所有标签（列表形式）
- Tag.articles：获取标签下的所有文章（dynamic query）
- 删除 Tag 时，SQLAlchemy 会自动级联删除 article_tags 中的关联记录（因 FK 定义在关联表中）

## 3. API 端点设计

### 3.1 标签路由（routes_tag.py）

Blueprint 名称：`tag_bp`，无 url_prefix。

#### POST /tags — 创建标签
```python
@tag_bp.route('/tags', methods=['POST'])
```
- **请求**：`{"name": "str"}`
- **逻辑**：
  1. 检查请求体中是否包含 `name` 且非空 → 400
  2. 查询数据库是否存在同名标签 → 409
  3. 创建 Tag 对象，`db.session.add()` + `db.session.commit()`
- **成功响应** (201)：`{"status": "ok", "data": {"id": int, "name": str}}`

#### GET /tags — 获取所有标签
```python
@tag_bp.route('/tags', methods=['GET'])
```
- **逻辑**：`Tag.query.all()`
- **成功响应** (200)：`{"status": "ok", "data": [{"id": int, "name": str}, ...]}`

#### PUT /tags/<id> — 编辑标签名称
```python
@tag_bp.route('/tags/<int:id>', methods=['PUT'])
```
- **请求**：`{"name": "str"}`
- **逻辑**：
  1. 查找标签，不存在 → 404
  2. 检查 `name` 是否存在且非空 → 400
  3. 检查新名称是否与其他标签重复（排除自身）→ 409
  4. 更新 `tag.name`，`db.session.commit()`
- **成功响应** (200)：`{"status": "ok", "data": {"id": int, "name": str}}`

#### DELETE /tags/<id> — 删除标签
```python
@tag_bp.route('/tags/<int:id>', methods=['DELETE'])
```
- **逻辑**：
  1. 查找标签，不存在 → 404
  2. `db.session.delete(tag)` + `db.session.commit()`
  3. SQLAlchemy 自动级联删除 article_tags 中的关联记录
- **成功响应** (200)：`{"status": "ok", "data": {"message": "Tag deleted"}}`

### 3.2 文章路由（routes_article.py）

Blueprint 名称：`article_bp`，无 url_prefix。

#### POST /articles — 创建文章
```python
@article_bp.route('/articles', methods=['POST'])
```
- **请求**：`{"title": "str", "body": "str"}`
- **逻辑**：
  1. 检查 `title` 和 `body` 是否存在 → 400
  2. 创建 Article 对象，`db.session.add()` + `db.session.commit()`
- **成功响应** (201)：`{"status": "ok", "data": {"id": int, "title": str, "body": str}}`

#### GET /articles — 列出所有文章（支持标签筛选）
```python
@article_bp.route('/articles', methods=['GET'])
```
- **查询参数**：`tag`（标签名称）、`tag_id`（标签 ID）
- **逻辑**：
  1. 检查 `tag` 参数 → 查找对应 Tag → 通过 `tag.articles` 获取文章列表
  2. 检查 `tag_id` 参数 → 查找对应 Tag → 通过 `tag.articles` 获取文章列表
  3. 无参数 → `Article.query.all()`
  4. **筛选优先级**：优先使用 `tag_id`，其次使用 `tag`（或反之，任选其一即可，因测试不会同时传递两个参数）
- **成功响应** (200)：`{"status": "ok", "data": [{"id": int, "title": str, "body": str}, ...]}`

#### GET /articles/<id> — 获取单篇文章
```python
@article_bp.route('/articles/<int:id>', methods=['GET'])
```
- **逻辑**：`Article.query.get(id)`，不存在 → 404
- **成功响应** (200)：`{"status": "ok", "data": {"id": int, "title": str, "body": str}}`

#### POST /articles/<id>/tags — 为文章绑定标签
```python
@article_bp.route('/articles/<int:id>/tags', methods=['POST'])
```
- **请求**：`{"tag_ids": [int, ...]}`
- **逻辑**：
  1. 查找文章，不存在 → 404
  2. 遍历 `tag_ids`，查找每个 Tag → 任一不存在 → 400
  3. 将 Tag 追加到 `article.tags`（SQLAlchemy 自动处理重复）
  4. `db.session.commit()`
- **成功响应** (200)：`{"status": "ok", "data": {"message": "Tags bound"}}`

#### GET /articles/<id>/tags — 获取文章的所有标签
```python
@article_bp.route('/articles/<int:id>/tags', methods=['GET'])
```
- **逻辑**：查找文章，不存在 → 404；返回 `article.tags` 列表
- **成功响应** (200)：`{"status": "ok", "data": [{"id": int, "name": str}, ...]}`

#### DELETE /articles/<id>/tags/<tag_id> — 解除关联
```python
@article_bp.route('/articles/<int:id>/tags/<int:tag_id>', methods=['DELETE'])
```
- **逻辑**：
  1. 查找文章，不存在 → 404
  2. 查找标签
  3. 如果标签在文章的 tags 列表中，移除
  4. `db.session.commit()`
- **成功响应** (200)：`{"status": "ok", "data": {"message": "Tag unbound"}}`

## 4. 关键实现细节

### 4.1 模块导入依赖

routes_tag.py 和 routes_article.py 都需要：
```python
from app import db
from models import Article, Tag, article_tags
```

### 4.2 序列化辅助函数

为避免重复代码，每个路由模块中定义序列化函数：

```python
# routes_tag.py
def tag_to_dict(tag):
    return {"id": tag.id, "name": tag.name}

# routes_article.py
def article_to_dict(article):
    return {"id": article.id, "title": article.title, "body": article.body}
```

### 4.3 标签筛选实现方案

```python
# GET /articles?tag=Python 或 ?tag_id=1
tag_name = request.args.get('tag')
tag_id = request.args.get('tag_id')

if tag_id:
    tag = Tag.query.get(int(tag_id))
    articles = tag.articles.all() if tag else []
elif tag_name:
    tag = Tag.query.filter_by(name=tag_name).first()
    articles = tag.articles.all() if tag else []
else:
    articles = Article.query.all()
```

### 4.4 绑定标签实现方案

```python
# POST /articles/<id>/tags
tag_ids = request.json.get('tag_ids', [])
tags = []
for tid in tag_ids:
    tag = Tag.query.get(tid)
    if not tag:
        return jsonify({"status": "error", "message": f"Tag {tid} not found"}), 400
    tags.append(tag)
article.tags.extend(tags)  # SQLAlchemy 自动处理重复（多对多表有联合主键）
db.session.commit()
```

### 4.5 删除标签的级联行为

SQLAlchemy 在删除 Tag 对象时，会自动级联删除 article_tags 中的关联记录（因为 FK 定义在关联表上，默认行为）。无需额外代码处理。

### 4.6 错误处理统一模式

所有错误响应使用统一格式：
```python
return jsonify({"status": "error", "message": "描述"}), <status_code>
```

## 5. 实现计划（ATU 执行顺序）

| 顺序 | ATU | 文件 | 依赖 | 复杂度 |
|------|-----|------|------|--------|
| 1 | ATU-003 | starter/routes_tag.py | ATU-002 | M |
| 2 | ATU-004 | starter/routes_article.py | ATU-003 | L |

**执行顺序说明**：先实现 routes_tag.py（标签 CRUD），因为 routes_article.py 中的文章标签绑定功能依赖 Tag 模型的正确性。

## 6. 测试映射

| 测试用例 | 验证的需求 |
|---------|-----------|
| test_create_article | FR-ART-01 |
| test_list_articles | FR-ART-02（无筛选） |
| test_get_article | FR-ART-03 |
| test_create_article_missing_fields | FR-ART-01 错误处理 |
| test_create_tag | FR-TAG-01 |
| test_create_tag_duplicate | FR-TAG-01 错误处理 |
| test_create_tag_no_name | FR-TAG-01 错误处理 |
| test_list_tags | FR-TAG-02 |
| test_update_tag | FR-TAG-03 |
| test_delete_tag | FR-TAG-04 |
| test_bind_tags_to_article | FR-ART-04 |
| test_get_article_tags | FR-ART-05 |
| test_unbind_tag_from_article | FR-ART-06 |
| test_delete_tag_removes_bindings | FR-TAG-04 级联行为 |
| test_filter_by_tag_name | FR-ART-02（tag 参数） |
| test_filter_by_tag_id | FR-ART-02（tag_id 参数） |
| test_filter_no_match | FR-ART-02（无匹配） |
| test_no_filter_returns_all | FR-ART-02（无参数） |
