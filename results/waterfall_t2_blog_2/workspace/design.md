# 方案设计文档 — T2-1 小型博客系统（文章标签管理 + 按标签筛选）

## 1. 数据库表设计

### 1.1 表结构

**article 表**

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY, AUTOINCREMENT | 自增主键 |
| title | VARCHAR(200) | NOT NULL | 文章标题 |
| body | TEXT | NOT NULL | 文章正文 |

**tag 表**

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY, AUTOINCREMENT | 自增主键 |
| name | VARCHAR(80) | UNIQUE, NOT NULL | 标签名称 |

**article_tags 关联表**

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| article_id | INTEGER | FK→article.id, PRIMARY KEY | 文章 ID |
| tag_id | INTEGER | FK→tag.id, PRIMARY KEY | 标签 ID |

### 1.2 级联删除策略

- 删除 Tag 时：SQLAlchemy 的 `relationship(backref=...)` 默认不会级联删除关联表记录。需要在 `routes_tag.py` 的 DELETE 端点中**手动删除** `article_tags` 中的关联记录，或者使用 `db.session.delete(tag)` 后 `db.session.commit()` 依赖数据库外键的 CASCADE 行为。
- **推荐方案**：在 DELETE `/tags/<id>` 中先手动清除关联记录，再删除标签。这是因为 SQLite 的外键 CASCADE 需要额外配置（`PRAGMA foreign_keys=ON`），而 Flask-SQLAlchemy 默认不启用。

## 2. API 端点设计

### 2.1 标签路由（routes_tag.py）— ATU-003

**完整 import（文件顶部）**：
```python
from flask import Blueprint, request, jsonify
from app import db
from models import Tag, article_tags
```

#### POST /tags — 创建标签

```python
@tag_bp.route('/tags', methods=['POST'])
def create_tag():
    data = request.get_json()
    # 验证：name 存在且非空
    if not data or not data.get('name'):
        return jsonify({"status": "error", "message": "name is required"}), 400
    # 验证：name 唯一性
    existing = Tag.query.filter_by(name=data['name']).first()
    if existing:
        return jsonify({"status": "error", "message": "Tag already exists"}), 409
    tag = Tag(name=data['name'])
    db.session.add(tag)
    db.session.commit()
    return jsonify({"status": "ok", "data": {"id": tag.id, "name": tag.name}}), 201
```

#### GET /tags — 获取所有标签

```python
@tag_bp.route('/tags', methods=['GET'])
def list_tags():
    tags = Tag.query.all()
    return jsonify({"status": "ok", "data": [{"id": t.id, "name": t.name} for t in tags]}), 200
```

#### PUT /tags/<id> — 编辑标签名称

```python
@tag_bp.route('/tags/<int:id>', methods=['PUT'])
def update_tag(id):
    tag = Tag.query.get(id)
    if not tag:
        return jsonify({"status": "error", "message": "Tag not found"}), 404
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({"status": "error", "message": "name is required"}), 400
    existing = Tag.query.filter_by(name=data['name']).first()
    if existing and existing.id != id:
        return jsonify({"status": "error", "message": "Tag name already exists"}), 409
    tag.name = data['name']
    db.session.commit()
    return jsonify({"status": "ok", "data": {"id": tag.id, "name": tag.name}}), 200
```

#### DELETE /tags/<id> — 删除标签（级联解除关联）

```python
@tag_bp.route('/tags/<int:id>', methods=['DELETE'])
def delete_tag(id):
    tag = Tag.query.get(id)
    if not tag:
        return jsonify({"status": "error", "message": "Tag not found"}), 404
    # 手动清除关联（避免依赖 SQLite CASCADE）
    db.session.execute(article_tags.delete().where(article_tags.c.tag_id == id))
    db.session.delete(tag)
    db.session.commit()
    return jsonify({"status": "ok", "data": {"message": "Tag deleted"}}), 200
```

**关键设计决策**：
- 使用 `article_tags.delete().where(...)` 手动清除关联，确保 `test_delete_tag_removes_bindings` 测试通过
- 409 冲突检查需排除自身（`existing.id != id`）

### 2.2 文章路由（routes_article.py）— ATU-004

**完整 import（文件顶部）**：
```python
from flask import Blueprint, request, jsonify
from app import db
from models import Article, Tag
```

#### POST /articles — 创建文章

```python
@article_bp.route('/articles', methods=['POST'])
def create_article():
    data = request.get_json()
    if not data or not data.get('title') or not data.get('body'):
        return jsonify({"status": "error", "message": "title and body are required"}), 400
    article = Article(title=data['title'], body=data['body'])
    db.session.add(article)
    db.session.commit()
    return jsonify({"status": "ok", "data": {"id": article.id, "title": article.title, "body": article.body}}), 201
```

#### GET /articles — 列出所有文章（支持按标签筛选）

```python
@article_bp.route('/articles', methods=['GET'])
def list_articles():
    tag_name = request.args.get('tag')
    tag_id = request.args.get('tag_id')

    if tag_name:
        tag = Tag.query.filter_by(name=tag_name).first()
        if tag:
            articles = tag.articles.all()  # lazy='dynamic' 支持 .all()
        else:
            articles = []
    elif tag_id:
        tag = Tag.query.get(int(tag_id))
        if tag:
            articles = tag.articles.all()
        else:
            articles = []
    else:
        articles = Article.query.all()

    return jsonify({"status": "ok", "data": [{"id": a.id, "title": a.title, "body": a.body} for a in articles]}), 200
```

**关键设计决策**：
- 使用 `tag.articles.all()` 利用 models.py 中定义的 `lazy='dynamic'` backref
- 筛选无匹配标签时返回空列表（满足 AC-17）

#### GET /articles/<id> — 获取单篇文章

```python
@article_bp.route('/articles/<int:id>', methods=['GET'])
def get_article(id):
    article = Article.query.get(id)
    if not article:
        return jsonify({"status": "error", "message": "Article not found"}), 404
    return jsonify({"status": "ok", "data": {"id": article.id, "title": article.title, "body": article.body}}), 200
```

#### POST /articles/<id>/tags — 绑定标签到文章

```python
@article_bp.route('/articles/<int:id>/tags', methods=['POST'])
def bind_tags(id):
    article = Article.query.get(id)
    if not article:
        return jsonify({"status": "error", "message": "Article not found"}), 404
    data = request.get_json()
    tag_ids = data.get('tag_ids', [])
    for tid in tag_ids:
        tag = Tag.query.get(tid)
        if tag and tag not in article.tags:
            article.tags.append(tag)
    db.session.commit()
    return jsonify({"status": "ok", "data": {"message": "Tags bound"}}), 200
```

**关键设计决策**：
- 使用 `tag not in article.tags` 检查避免重复绑定（幂等操作）
- 测试用例只验证有效 tag_id，不验证不存在的 tag_id 场景

#### GET /articles/<id>/tags — 获取文章标签

```python
@article_bp.route('/articles/<int:id>/tags', methods=['GET'])
def get_article_tags(id):
    article = Article.query.get(id)
    if not article:
        return jsonify({"status": "error", "message": "Article not found"}), 404
    return jsonify({"status": "ok", "data": [{"id": t.id, "name": t.name} for t in article.tags]}), 200
```

#### DELETE /articles/<id>/tags/<tag_id> — 解除标签绑定

```python
@article_bp.route('/articles/<int:id>/tags/<int:tag_id>', methods=['DELETE'])
def unbind_tag(id, tag_id):
    article = Article.query.get(id)
    if not article:
        return jsonify({"status": "error", "message": "Article not found"}), 404
    tag = Tag.query.get(tag_id)
    if tag in article.tags:
        article.tags.remove(tag)
        db.session.commit()
    return jsonify({"status": "ok", "data": {"message": "Tag unbound"}}), 200
```

## 3. 关键算法逻辑

### 3.1 标签筛选文章（GET /articles?tag=&tag_id=）

```
输入：GET /articles?tag=Python 或 GET /articles?tag_id=1
处理流程：
  1. 检查查询参数 tag 或 tag_id
  2. 如果提供了 tag：通过 Tag.query.filter_by(name=tag_name) 查找标签
  3. 如果提供了 tag_id：通过 Tag.query.get(tag_id) 查找标签
  4. 如果找到标签：返回 tag.articles.all()（通过 lazy='dynamic' backref）
  5. 如果未找到标签：返回空列表 []
  6. 如果未提供筛选参数：返回 Article.query.all()
输出：{"status": "ok", "data": [...]}
```

### 3.2 级联删除标签（DELETE /tags/<id>）

```
输入：DELETE /tags/1
处理流程：
  1. 查找标签，不存在则返回 404
  2. 执行 article_tags.delete().where(article_tags.c.tag_id == id) 清除关联
  3. 删除标签对象
  4. db.session.commit()
输出：{"status": "ok", "data": {"message": "Tag deleted"}}
```

## 4. 模块依赖关系

```
app.py（不可修改）
  ├── db = SQLAlchemy()                    # 模块级别创建，可安全导入
  ├── from models import Article, Tag      # 在 create_app() 内导入
  ├── from routes_article import article_bp
  └── from routes_tag import tag_bp

routes_tag.py — 完整 import：
  ├── from flask import Blueprint, request, jsonify
  ├── from app import db                   # db 在 app.py 模块级别创建
  ├── from models import Tag, article_tags # Tag 模型 + 关联表（用于级联删除）
  └── tag_bp = Blueprint('tag_bp', __name__)  # 已在骨架中定义

routes_article.py — 完整 import：
  ├── from flask import Blueprint, request, jsonify
  ├── from app import db                   # db 在 app.py 模块级别创建
  ├── from models import Article, Tag      # 文章模型 + 标签模型（用于筛选）
  └── article_bp = Blueprint('article_bp', __name__)  # 已在骨架中定义
```

**重要**：
- `db` 在 `app.py` 第 12 行模块级别创建（`db = SQLAlchemy()`），不在 `create_app()` 内部，因此通过 `from app import db` 导入是安全的。
- `models.py` 中 `from app import db` 也基于同样的原因可以工作。
- **不要**从 `models.py` 导入 `db`（`models.py` 不导出 `db`），必须从 `app.py` 导入。

## 5. 实现计划与 ATU 执行顺序

### 阶段 3：开发实现

| 顺序 | ATU | 文件 | 描述 | 依赖 |
|------|-----|------|------|------|
| 1 | ATU-003 | `starter/routes_tag.py` | 实现标签 CRUD 4 个端点 | design.md |
| 2 | ATU-004 | `starter/routes_article.py` | 实现文章 CRUD + 标签绑定 + 筛选 6 个端点 | ATU-003 |

**执行策略**：
- ATU-003 先实现，因为它较简单且独立
- ATU-004 依赖 ATU-003（文章筛选功能需要 Tag 模型可用）
- 每个 ATU 完成后立即运行测试验证，确保渐进式通过

### 阶段 4：测试验证

- ATU-005：运行完整测试套件，确保所有 18 个测试用例通过

## 6. 错误处理汇总

| 场景 | HTTP 状态码 | 响应体 |
|------|-------------|--------|
| 缺少必填字段 | 400 | `{"status": "error", "message": "..."}` |
| 资源不存在 | 404 | `{"status": "error", "message": "..."}` |
| 重复创建 | 409 | `{"status": "error", "message": "..."}` |
| 成功创建 | 201 | `{"status": "ok", "data": {...}}` |
| 成功操作 | 200 | `{"status": "ok", "data": {...}}` |
