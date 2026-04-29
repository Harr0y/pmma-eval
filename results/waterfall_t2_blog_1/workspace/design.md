# 方案设计文档 — T2-1 小型博客系统

## 1. 架构概览

```
app.py (不可修改)
  ├── models.py        → Article, Tag, article_tags（已定义，无需修改）
  ├── routes_tag.py    → tag_bp Blueprint（待实现）
  └── routes_article.py → article_bp Blueprint（待实现）
```

### 模块依赖关系
```
routes_tag.py ──import──→ models.py (Tag, db)
routes_article.py ──import──→ models.py (Article, Tag, db)
app.py ──import──→ models.py, routes_tag.py, routes_article.py
```

## 2. 数据模型设计

**结论：models.py 无需修改。** 当前定义已完全满足需求：

```python
# article_tags 关联表
article_tags = db.Table('article_tags',
    db.Column('article_id', db.Integer, db.ForeignKey('article.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

# Article 模型
class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    tags = db.relationship('Tag', secondary=article_tags,
                           backref=db.backref('articles', lazy='dynamic'))

# Tag 模型
class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
```

### 级联删除设计
- 删除 Tag 时，SQLAlchemy 通过 `article_tags` 表的 ForeignKey 自动级联删除关联记录
- 但需要显式处理：删除 Tag 前/后清理 article_tags 记录，或依赖数据库的 ON DELETE CASCADE
- **推荐方案**：使用 `db.session.delete(tag)` 后 `db.session.commit()`，SQLAlchemy 会处理关联表清理（因为 relationship 配置正确）
- **备选方案**：如果 SQLAlchemy 不自动清理，则手动执行 `db.session.execute(article_tags.delete().where(article_tags.c.tag_id == tag.id))`

## 3. API 端点设计

### 3.1 标签路由（routes_tag.py）

#### 3.1.1 POST /tags — 创建标签
```python
@tag_bp.route('/tags', methods=['POST'])
def create_tag():
    data = request.get_json()
    # 验证：name 必须存在且非空字符串
    name = data.get('name')
    if not name or not name.strip():
        return jsonify({"status": "error", "message": "Name is required"}), 400
    # 检查唯一性
    existing = Tag.query.filter_by(name=name).first()
    if existing:
        return jsonify({"status": "error", "message": "Tag already exists"}), 409
    # 创建
    tag = Tag(name=name)
    db.session.add(tag)
    db.session.commit()
    return jsonify({"status": "ok", "data": {"id": tag.id, "name": tag.name}}), 201
```

#### 3.1.2 GET /tags — 获取标签列表
```python
@tag_bp.route('/tags', methods=['GET'])
def list_tags():
    tags = Tag.query.all()
    return jsonify({"status": "ok", "data": [{"id": t.id, "name": t.name} for t in tags]}), 200
```

#### 3.1.3 PUT /tags/<id> — 编辑标签名称
```python
@tag_bp.route('/tags/<int:id>', methods=['PUT'])
def update_tag(id):
    data = request.get_json()
    name = data.get('name')
    # 验证：name 必须存在
    if not name or not name.strip():
        return jsonify({"status": "error", "message": "Name is required"}), 400
    # 查找标签
    tag = Tag.query.get(id)
    if not tag:
        return jsonify({"status": "error", "message": "Tag not found"}), 404
    # 检查唯一性（排除自身）
    existing = Tag.query.filter(Tag.name == name, Tag.id != id).first()
    if existing:
        return jsonify({"status": "error", "message": "Tag name already exists"}), 409
    tag.name = name
    db.session.commit()
    return jsonify({"status": "ok", "data": {"id": tag.id, "name": tag.name}}), 200
```

#### 3.1.4 DELETE /tags/<id> — 删除标签
```python
@tag_bp.route('/tags/<int:id>', methods=['DELETE'])
def delete_tag(id):
    tag = Tag.query.get(id)
    if not tag:
        return jsonify({"status": "error", "message": "Tag not found"}), 404
    # 清理关联记录（确保级联删除）
    db.session.execute(article_tags.delete().where(article_tags.c.tag_id == id))
    db.session.delete(tag)
    db.session.commit()
    return jsonify({"status": "ok", "data": {"message": "Tag deleted"}}), 200
```

### 3.2 文章路由（routes_article.py）

#### 3.2.1 GET /articles — 列出文章（支持筛选）
```python
@article_bp.route('/articles', methods=['GET'])
def list_articles():
    tag_name = request.args.get('tag')
    tag_id = request.args.get('tag_id')
    query = Article.query
    if tag_name:
        query = query.join(Article.tags).filter(Tag.name == tag_name)
    elif tag_id:
        query = query.join(Article.tags).filter(Tag.id == tag_id)
    articles = query.all()
    return jsonify({"status": "ok", "data": [{"id": a.id, "title": a.title, "body": a.body} for a in articles]}), 200
```

#### 3.2.2 POST /articles — 创建文章
```python
@article_bp.route('/articles', methods=['POST'])
def create_article():
    data = request.get_json()
    title = data.get('title')
    body = data.get('body')
    if not title or not body:
        return jsonify({"status": "error", "message": "Title and body are required"}), 400
    article = Article(title=title, body=body)
    db.session.add(article)
    db.session.commit()
    return jsonify({"status": "ok", "data": {"id": article.id, "title": article.title, "body": article.body}}), 201
```

#### 3.2.3 GET /articles/<id> — 获取单篇文章
```python
@article_bp.route('/articles/<int:id>', methods=['GET'])
def get_article(id):
    article = Article.query.get(id)
    if not article:
        return jsonify({"status": "error", "message": "Article not found"}), 404
    return jsonify({"status": "ok", "data": {"id": article.id, "title": article.title, "body": article.body}}), 200
```

#### 3.2.4 POST /articles/<id>/tags — 绑定标签
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
        if not tag:
            return jsonify({"status": "error", "message": f"Tag {tid} not found"}), 400
        if tag not in article.tags:
            article.tags.append(tag)
    db.session.commit()
    return jsonify({"status": "ok", "data": {"message": "Tags bound"}}), 200
```

#### 3.2.5 GET /articles/<id>/tags — 获取文章标签
```python
@article_bp.route('/articles/<int:id>/tags', methods=['GET'])
def get_article_tags(id):
    article = Article.query.get(id)
    if not article:
        return jsonify({"status": "error", "message": "Article not found"}), 404
    return jsonify({"status": "ok", "data": [{"id": t.id, "name": t.name} for t in article.tags]}), 200
```

#### 3.2.6 DELETE /articles/<id>/tags/<tag_id> — 解除关联
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

## 4. 关键设计决策

### 4.1 级联删除策略
- **主动清理方案**：DELETE /tags/<id> 时，先手动删除 article_tags 中的关联记录，再删除 Tag
- **原因**：SQLite 默认不启用外键约束，无法依赖数据库级 ON DELETE CASCADE。手动清理确保关联记录被正确移除
- **测试验证**：`test_delete_tag_removes_bindings` 测试用例验证此行为

### 4.2 标签筛选实现
- 使用 SQLAlchemy 的 `join` + `filter` 实现多对多关系筛选
- `?tag=Name` 通过 Tag.name 过滤
- `?tag_id=N` 通过 Tag.id 过滤
- 两个参数互斥（tag_name 优先）

### 4.3 输入验证策略
- `not name or not name.strip()`：同时处理缺失（None）和空字符串（""/"  "）情况
- 这覆盖了 `test_create_tag_no_name` 中 `json={}` 的场景（data.get('name') 返回 None）

### 4.4 错误处理统一模式
所有端点统一使用 `{"status": "error", "message": "..."}` 格式返回错误信息。

## 5. 实现计划（ATU 执行顺序）

| 顺序 | ATU ID | 描述 | 修改文件 | 预估行数 |
|------|--------|------|----------|----------|
| 1 | ATU-003 | 实现标签 CRUD 路由 | starter/routes_tag.py | ~60 行 |
| 2 | ATU-004 | 实现文章路由 | starter/routes_article.py | ~80 行 |

**执行顺序说明**：
- ATU-003 先于 ATU-004：标签路由是独立模块，先实现可独立测试
- ATU-004 依赖 ATU-003：文章标签绑定功能需要 Tag 模型可用

## 6. 模块 Import 设计

### routes_tag.py
```python
from flask import Blueprint, request, jsonify
from models import Tag, db, article_tags
```

### routes_article.py
```python
from flask import Blueprint, request, jsonify
from models import Article, Tag, db
```

**注意**：routes_article.py 不需要直接 import article_tags（筛选通过 relationship join 实现，绑定/解绑通过 relationship 操作实现）。

## 7. 需求规避（来自 Reviewer 警告）

- 无需规避项：Reviewer 审批时未提出警告
