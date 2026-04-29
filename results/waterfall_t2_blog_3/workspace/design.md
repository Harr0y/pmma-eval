# 方案设计文档 — T2-1 小型博客系统

## 1. 数据库设计

### 1.1 表结构

#### article 表
| 字段 | 类型 | 约束 |
|------|------|------|
| id | INTEGER | PRIMARY KEY, AUTOINCREMENT |
| title | VARCHAR(200) | NOT NULL |
| body | TEXT | NOT NULL |

#### tag 表
| 字段 | 类型 | 约束 |
|------|------|------|
| id | INTEGER | PRIMARY KEY, AUTOINCREMENT |
| name | VARCHAR(80) | NOT NULL, UNIQUE |

#### article_tags 关联表
| 字段 | 类型 | 约束 |
|------|------|------|
| article_id | INTEGER | FK → article.id, PRIMARY KEY |
| tag_id | INTEGER | FK → tag.id, PRIMARY KEY |

### 1.2 模型关系

```
Article ←→ article_tags ←→ Tag
(多对多)
```

- Article.tags → 通过 `secondary=article_tags` 访问关联 Tag 列表
- Tag.articles → 通过 `backref('articles', lazy='dynamic')` 访问关联 Article 列表

**注意**：`lazy='dynamic'` 在 SQLAlchemy 2.0+ 中已被标记为 deprecated，但 Flask-SQLAlchemy 3.1 当前仍支持。由于 `models.py` 中已有此设置且不可大幅修改模型结构，我们保留 `lazy='dynamic'` 但需注意其行为：返回 AppenderQuery 对象，需要 `.all()` 获取列表。

### 1.3 级联删除策略

删除 Tag 时：
1. 先通过 `article_tags.delete()` 显式删除 article_tags 中的关联记录
2. 再删除 Tag 本身

**设计决策**：采用代码中显式删除关联的方式，不依赖数据库级 FK CASCADE。原因：
- SQLite 的 CASCADE 需要额外 PRAGMA 配置
- 代码方式更可控、更易调试

## 2. API 端点设计

### 2.1 文章路由 (routes_article.py)

| 方法 | 路径 | 功能 | 请求体 | 成功码 | 错误码 |
|------|------|------|--------|--------|--------|
| GET | /articles | 列出文章（可选筛选） | — | 200 | — |
| POST | /articles | 创建文章 | {title, body} | 201 | 400（缺少 title 或 body） |
| GET | /articles/\<id\> | 获取文章详情 | — | 200 | 404（文章不存在） |
| POST | /articles/\<id\>/tags | 绑定标签 | {tag_ids:[]} | 200 | 404（文章不存在）, 400（标签不存在） |
| GET | /articles/\<id\>/tags | 获取文章标签 | — | 200 | 404（文章不存在） |
| DELETE | /articles/\<id\>/tags/\<tag_id\> | 解绑标签 | — | 200 | 404（文章不存在） |

### 2.2 标签路由 (routes_tag.py)

| 方法 | 路径 | 功能 | 请求体 | 成功码 | 错误码 |
|------|------|------|--------|--------|--------|
| POST | /tags | 创建标签 | {name} | 201 | 400（name 缺失或为空）, 409（名称重复） |
| GET | /tags | 标签列表 | — | 200 | — |
| PUT | /tags/\<id\> | 编辑标签 | {name} | 200 | 400（name 缺失）, 404（标签不存在）, 409（名称与其他标签重复） |
| DELETE | /tags/\<id\> | 删除标签 | — | 200 | 404（标签不存在） |

## 3. 关键算法与实现逻辑

### 3.1 创建文章 (POST /articles)

```python
@article_bp.route('/articles', methods=['POST'])
def create_article():
    data = request.get_json()
    if not data or 'title' not in data or 'body' not in data:
        return error_response('Title and body are required', 400)

    article = Article(title=data['title'], body=data['body'])
    db.session.add(article)
    db.session.commit()

    return ok_response({
        'id': article.id,
        'title': article.title,
        'body': article.body
    }, 201)
```

**关键点**：
- `request.get_json()` 可能为 `None`（非 JSON 请求），需判空
- 必须同时检查 `title` 和 `body` 两个字段，缺少任一返回 400

### 3.2 获取单篇文章 (GET /articles/\<id\>)

```python
@article_bp.route('/articles/<int:article_id>', methods=['GET'])
def get_article(article_id):
    article = Article.query.get(article_id)
    if not article:
        return error_response('Article not found', 404)

    return ok_response({
        'id': article.id,
        'title': article.title,
        'body': article.body
    })
```

**关键点**：
- `Article.query.get()` 返回 `None` 时返回 404
- 使用 `<int:article_id>` 路由参数确保 ID 为整数

### 3.3 列出文章/按标签筛选 (GET /articles?tag=&tag_id=)

```python
@article_bp.route('/articles', methods=['GET'])
def list_articles():
    tag_name = request.args.get('tag')
    tag_id_str = request.args.get('tag_id')

    if tag_name:
        tag = Tag.query.filter_by(name=tag_name).first()
        articles = tag.articles.all() if tag else []
    elif tag_id_str:
        tag = Tag.query.get(int(tag_id_str))
        articles = tag.articles.all() if tag else []
    else:
        articles = Article.query.all()

    return ok_response([{
        'id': a.id,
        'title': a.title,
        'body': a.body
    } for a in articles])
```

**关键点**：
- `tag_id` 通过 `request.args.get('tag_id')` 获取，返回类型为 str，需 `int()` 转换
- 无匹配时返回空列表 `[]`，HTTP 状态码仍为 200
- `tag.articles` 使用 `lazy='dynamic'`，需要 `.all()` 获取列表

### 3.4 标签绑定 (POST /articles/\<id\>/tags)

```python
@article_bp.route('/articles/<int:article_id>/tags', methods=['POST'])
def bind_tags(article_id):
    article = Article.query.get(article_id)
    if not article:
        return error_response('Article not found', 404)

    data = request.get_json()
    tag_ids = data.get('tag_ids', []) if data else []
    for tid in tag_ids:
        tag = Tag.query.get(tid)
        if not tag:
            return error_response('Tag not found', 400)
        if tag not in article.tags:
            article.tags.append(tag)  # 幂等：已绑定的跳过

    db.session.commit()
    return ok_response({'message': 'Tags bound'})
```

**关键点**：
- 逐个验证 tag_id 是否存在，任何一个不存在即返回 400
- 幂等处理：已绑定的标签不会重复添加（`if tag not in article.tags`）

### 3.5 获取文章标签 (GET /articles/\<id\>/tags)

```python
@article_bp.route('/articles/<int:article_id>/tags', methods=['GET'])
def get_article_tags(article_id):
    article = Article.query.get(article_id)
    if not article:
        return error_response('Article not found', 404)

    return ok_response([{'id': t.id, 'name': t.name} for t in article.tags])
```

### 3.6 标签解绑 (DELETE /articles/\<id\>/tags/\<tag_id\>)

```python
@article_bp.route('/articles/<int:article_id>/tags/<int:tag_id>', methods=['DELETE'])
def unbind_tag(article_id, tag_id):
    article = Article.query.get(article_id)
    if not article:
        return error_response('Article not found', 404)

    tag = Tag.query.get(tag_id)
    if tag and tag in article.tags:
        article.tags.remove(tag)  # 幂等：未绑定的跳过

    db.session.commit()
    return ok_response({'message': 'Tag unbound'})
```

**关键点**：
- 幂等处理：未绑定的标签不报错（只检查文章是否存在）

### 3.7 创建标签 (POST /tags)

```python
@tag_bp.route('/tags', methods=['POST'])
def create_tag():
    data = request.get_json()
    if not data or not data.get('name'):
        return error_response('Name is required', 400)

    name = data['name']
    if not isinstance(name, str) or not name.strip():
        return error_response('Name is required', 400)

    existing = Tag.query.filter_by(name=name).first()
    if existing:
        return error_response('Tag already exists', 409)

    tag = Tag(name=name)
    db.session.add(tag)
    db.session.commit()

    return ok_response({'id': tag.id, 'name': tag.name}, 201)
```

**关键点**：
- `name` 缺失（key 不存在）或为空字符串均返回 400
- 使用 `data.get('name')` 同时处理 key 缺失和值为 `None` 的情况
- 创建前检查名称唯一性，重复返回 409

### 3.8 编辑标签 (PUT /tags/\<id\>)

```python
@tag_bp.route('/tags/<int:tag_id>', methods=['PUT'])
def update_tag(tag_id):
    tag = Tag.query.get(tag_id)
    if not tag:
        return error_response('Tag not found', 404)

    data = request.get_json()
    if not data or not data.get('name'):
        return error_response('Name is required', 400)

    new_name = data['name']
    # 检查新名称是否与其他标签重复（排除自身）
    existing = Tag.query.filter(Tag.name == new_name, Tag.id != tag_id).first()
    if existing:
        return error_response('Tag name already exists', 409)

    tag.name = new_name
    db.session.commit()

    return ok_response({'id': tag.id, 'name': tag.name})
```

**关键点**：
- 先检查标签是否存在（404）
- 再检查 name 是否提供（400）
- 最后检查新名称是否与其他标签重复，排除自身（`Tag.id != tag_id`）
- 409 冲突查询必须排除当前标签自身，否则编辑为相同名称也会报冲突

### 3.9 删除标签级联 (DELETE /tags/\<id\>)

```python
@tag_bp.route('/tags/<int:tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    tag = Tag.query.get(tag_id)
    if not tag:
        return error_response('Tag not found', 404)

    # 显式清除所有文章与该标签的关联（通过 article_tags 表直接操作）
    db.session.execute(article_tags.delete().where(article_tags.c.tag_id == tag_id))
    db.session.delete(tag)
    db.session.commit()

    return ok_response({'message': 'Tag deleted'})
```

**关键点**：
- 由于 Tag.articles 使用 `lazy='dynamic'`，不能直接赋值 `tag.articles = []`
- 需要通过 `db.session.execute(article_tags.delete()...)` 显式删除关联记录
- 必须先删关联再删 Tag 本身，避免 FK 约束冲突
- `from models import article_tags` 需要在 routes_tag.py 中导入

### 3.10 统一响应格式辅助函数

```python
def ok_response(data, status_code=200):
    return jsonify({"status": "ok", "data": data}), status_code

def error_response(message, status_code=400):
    return jsonify({"status": "error", "message": message}), status_code
```

## 4. 模块间依赖关系

```
app.py (不可修改)
  ├── 顶层: db = SQLAlchemy()
  └── create_app() 内延迟导入:
      ├── from models import Article, Tag
      ├── from routes_article import article_bp
      └── from routes_tag import tag_bp

models.py
  ├── 顶层: from app import db (依赖 app.py 已执行 db = SQLAlchemy())
  ├── article_tags 关联表 (db.Table)
  ├── Article 模型 (含 tags relationship)
  └── Tag 模型 (含 articles backref lazy='dynamic')

routes_article.py
  └── from models import db, Article, Tag

routes_tag.py
  └── from models import db, Tag, article_tags
```

**Import 时序（循环导入解决机制）**：
1. Python 首次 `import app` → 执行 `db = SQLAlchemy()` → `db` 已绑定到 `app` 模块
2. `import models` → 执行 `from app import db` → 成功（`app.db` 已存在）
3. `app.create_app()` 内 `from models import Article, Tag` → 成功（`models` 已加载完毕）
4. `routes_article.py` 和 `routes_tag.py` 通过 `from models import ...` 获取所有依赖

**不可修改此导入结构**，否则会破坏循环导入的解决机制。

## 5. 实现计划（ATU 执行顺序）

| 顺序 | ATU | 文件 | 说明 |
|------|-----|------|------|
| 1 | ATU-003 | starter/models.py | 确认数据模型完整性（当前 models.py 已基本完整，需验证） |
| 2 | ATU-004 | starter/routes_tag.py | 实现标签 CRUD（4 个端点：POST/GET/PUT/DELETE） |
| 3 | ATU-005 | starter/routes_article.py | 实现文章路由（6 个端点 + 筛选逻辑） |

**依赖说明**：
- ATU-003 是 ATU-004 和 ATU-005 的前置条件
- ATU-004 和 ATU-005 互相独立，但按顺序执行（先实现较简单的 Tag CRUD）

## 6. 风险与注意事项

1. **循环导入机制**：`models.py` 通过**顶层导入** `from app import db` 获取 db 对象；`app.py` 通过**延迟导入**（在 `create_app()` 函数体内）`from models import Article, Tag` 避免循环导入。`routes_article.py` 和 `routes_tag.py` 通过 `from models import ...` 获取所有依赖。**不可修改此导入结构。**

2. **lazy='dynamic' 弃用风险**：Tag.articles 的 `lazy='dynamic'` 在 SQLAlchemy 2.0+ 中已 deprecated，但 Flask-SQLAlchemy 3.1 当前仍支持。其行为：返回 AppenderQuery 对象（非列表），需要 `.all()` 获取列表，不能直接赋值清空。保留此设置是因为 models.py 中已定义且不能大幅修改模型结构。如需未来迁移，应改用 `lazy='select'` + 显式查询。

3. **article_tags 表的直接操作**：在 routes_tag.py 中需要 `from models import article_tags` 来执行原生 SQL 删除关联记录（`db.session.execute(article_tags.delete()...)`）。

4. **tag_id 参数类型**：`request.args.get('tag_id')` 返回字符串，需要 `int()` 转换后使用 `Tag.query.get()`。

5. **测试覆盖缺口**：以下场景 requirements.md 已定义行为但 test_basic.py 未覆盖测试，实现时仍需正确处理：
   - `GET /articles/<id>` 文章不存在返回 404（AC-3 定义但无对应测试）
   - `DELETE /tags/<id>` 标签不存在返回 404（AC-10 定义但无对应测试）
   - `DELETE /articles/<id>/tags/<tag_id>` 文章不存在返回 404（AC-13 定义但无对应测试）
   - `POST /tags` name 为空字符串 `{"name": ""}` 返回 400（AC-7 只测试了 key 缺失）
