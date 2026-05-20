# 方案设计文档 — T2-1 小型博客系统

## 1. 数据库表设计

### 1.1 article 表

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY, AUTO INCREMENT | 文章 ID |
| title | VARCHAR(200) | NOT NULL | 文章标题 |
| body | TEXT | NOT NULL | 文章正文 |

### 1.2 tag 表

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY, AUTO INCREMENT | 标签 ID |
| name | VARCHAR(80) | UNIQUE, NOT NULL | 标签名称 |

### 1.3 article_tags 关联表

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| article_id | INTEGER | FK(article.id), PRIMARY KEY | 文章 ID |
| tag_id | INTEGER | FK(tag.id), PRIMARY KEY | 标签 ID |

**ORM 映射**：Article.tags ↔ Tag.articles 通过 secondary=article_tags 关联。

**注意**：以上表结构已在 models.py 中实现，无需修改。

## 2. API 端点设计

### 2.1 标签路由（routes_tag.py）

#### POST /tags — 创建标签
```
输入: {"name": "Python"}
处理:
  1. 验证请求体为 JSON
  2. 提取 name 字段，若缺失或空字符串 → 返回 400
  3. 检查 name 是否已存在（Tag.query.filter_by(name=name).first()）→ 若存在返回 409
  4. 创建 Tag 对象，db.session.add() + db.session.commit()
输出: 201 {"status": "ok", "data": {"id": int, "name": str}}
```

#### GET /tags — 获取所有标签
```
处理:
  1. Tag.query.all()
  2. 序列化为 [{"id": int, "name": str}, ...]
输出: 200 {"status": "ok", "data": [...]}
```

#### PUT /tags/<id> — 编辑标签名称
```
输入: {"name": "NewName"}
处理:
  1. 验证请求体为 JSON
  2. 提取 name 字段，若缺失或空字符串 → 返回 400
  3. 查找 Tag.query.get(id)，若不存在 → 返回 404
  4. 检查新 name 是否与其他标签重复（排除自身：filter(Tag.id != tag_id)）→ 若与其他标签重复返回 409；若与自身相同视为无操作
  5. 更新 tag.name，db.session.commit()
输出: 200 {"status": "ok", "data": {"id": int, "name": str}}
```

#### DELETE /tags/<id> — 删除标签
```
处理:
  1. 查找 Tag.query.get(id)，若不存在 → 返回 404
  2. db.session.delete(tag) + db.session.commit()
     （SQLAlchemy 会自动级联删除 article_tags 中的关联记录）
输出: 200 {"status": "ok", "data": {"message": "Tag deleted"}}
```

**级联删除机制**：SQLAlchemy 的 relationship 配置中，删除 Tag 时会自动清除 article_tags 中的关联行（因为 article_tags 是 secondary 表，SQLAlchemy 默认处理）。

### 2.2 文章路由（routes_article.py）

#### POST /articles — 创建文章
```
输入: {"title": "Hello", "body": "World"}
处理:
  1. 验证请求体为 JSON
  2. 提取 title 和 body 字段，若任一缺失 → 返回 400
  3. 创建 Article 对象，db.session.add() + db.session.commit()
输出: 201 {"status": "ok", "data": {"id": int, "title": str, "body": str}}
```

#### GET /articles — 列出文章（可选标签筛选）
```
查询参数: ?tag=<name> 或 ?tag_id=<id>
处理:
  1. 若提供 tag 参数:
     - 查找 Tag.query.filter_by(name=tag).first()
     - 若标签存在: 查询 tag.articles.all()
     - 若标签不存在: 返回空列表 []
  2. 若提供 tag_id 参数（且无 tag 参数）:
     - 查找 Tag.query.get(tag_id)
     - 若标签存在: 查询 tag.articles.all()
     - 若标签不存在: 返回空列表 []
  3. 若无筛选参数:
     - Article.query.all()
  4. 序列化为 [{"id": int, "title": str, "body": str}, ...]
输出: 200 {"status": "ok", "data": [...]}
```

**筛选优先级**：tag 参数优先于 tag_id 参数（requirements.md 7.2 节定义）。

#### GET /articles/<id> — 获取单篇文章
```
处理:
  1. Article.query.get(id)，若不存在 → 返回 404
  2. 序列化为 {"id": int, "title": str, "body": str}
输出: 200 {"status": "ok", "data": {...}}
```

**注**：id 参数为整数类型，由 Flask 路由的 `<int:id>` 约束保证。若传入非整数，Flask 自动返回 404。

#### POST /articles/<id>/tags — 绑定标签到文章
```
输入: {"tag_ids": [1, 2]}
处理:
  1. 查找 Article.query.get(id)，若不存在 → 返回 404
  2. 若 tag_ids 为空数组 [] → 幂等处理，直接返回 200
  3. 遍历 tag_ids，对每个 tag_id:
     - 查找 Tag.query.get(tag_id)
     - 若标签不存在 → 立即返回 400（不继续遍历）
     - 将 tag 添加到 article.tags（自动去重，已绑定的不会重复添加）
  4. db.session.commit()
输出: 200 {"status": "ok", "data": {"message": "Tags bound"}}
```

**边界条件**：
- 空 tag_ids 数组 `[]`：幂等返回 200
- tag_ids 中存在不存在的标签：遇到第一个即返回 400，不继续遍历

#### GET /articles/<id>/tags — 获取文章的所有标签
```
处理:
  1. 查找 Article.query.get(id)，若不存在 → 返回 404
  2. 获取 article.tags，序列化为 [{"id": int, "name": str}, ...]
输出: 200 {"status": "ok", "data": [...]}
```

#### DELETE /articles/<id>/tags/<tag_id> — 解除关联
```
处理:
  1. 查找 Article.query.get(id)，若不存在 → 返回 404
  2. 查找 Tag.query.get(tag_id)
  3. 场景 A：Tag 记录不存在（数据库中无此标签）→ 幂等处理，仍返回 200
  4. 场景 B：Tag 存在但未与该文章关联 → 幂等处理，仍返回 200
  5. 场景 C：Tag 存在且与该文章关联 → article.tags.remove(tag)，db.session.commit()
输出: 200 {"status": "ok", "data": {"message": "Tag unbound"}}
```

**幂等策略**：无论 Tag 是否存在或是否已关联，均返回 200（requirements.md 7.1 节定义）。

## 3. 关键算法逻辑

### 3.1 标签名唯一性检查
创建和编辑标签时，需检查名称唯一性。使用 SQLAlchemy 的 `filter_by(name=name).first()` 查询。编辑时需排除自身：`filter_by(name=name).filter(Tag.id != tag_id).first()`。若新名称与自身相同（无实际修改），因排除了自身不会触发 409，直接更新为相同值（无操作）。

### 3.2 文章标签筛选
通过 ORM relationship 实现：先查 Tag，再通过 `tag.articles` 获取关联文章。这利用了 SQLAlchemy 的多对多关系，无需手动 JOIN。

### 3.3 级联删除
删除 Tag 时，SQLAlchemy 自动处理 secondary 表（article_tags）中的关联记录清除。无需手动删除关联。

## 4. 错误处理策略

| 场景 | HTTP 状态码 | 响应格式 |
|------|------------|----------|
| 缺少必填字段 | 400 | `{"status": "error", "message": "具体缺失字段"}` |
| 资源不存在 | 404 | `{"status": "error", "message": "资源未找到"}` |
| 名称重复 | 409 | `{"status": "error", "message": "名称已存在"}` |
| 请求体非 JSON | 400 | `{"status": "error", "message": "请求体必须是 JSON"}` |

## 5. 实现计划

### ATU 全景

| ATU ID | 阶段 | 描述 | 状态 |
|--------|------|------|------|
| ATU-001 | requirements | 需求分析文档 requirements.md | Done |
| ATU-002 | design | 方案设计文档 design.md | In Review |
| ATU-003 | implementation | 标签 CRUD 路由（routes_tag.py） | Open |
| ATU-004 | implementation | 文章路由（routes_article.py） | Open |

### 开发 ATU 拆分与执行顺序

| 顺序 | ATU ID | 文件 | 描述 | 复杂度 |
|------|--------|------|------|--------|
| 1 | ATU-003 | starter/routes_tag.py | 标签 CRUD 路由（4 个接口） | M |
| 2 | ATU-004 | starter/routes_article.py | 文章路由（6 个接口） | L |

**依赖关系**：
- ATU-003 和 ATU-004 均依赖 ATU-002（设计文档），可按顺序实现
- ATU-003 先实现（标签是基础实体，文章路由依赖标签存在）
- ATU-004 后实现（文章路由包含标签绑定逻辑，依赖标签模型）

### 模块间 import 依赖
```
routes_tag.py → models (Tag, db)
routes_article.py → models (Article, Tag, db)
```

## 6. 数据序列化格式

### Article 序列化
```python
{"id": article.id, "title": article.title, "body": article.body}
```

### Tag 序列化
```python
{"id": tag.id, "name": tag.name}
```
