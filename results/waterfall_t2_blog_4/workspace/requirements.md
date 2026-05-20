# 需求分析文档 — T2-1 小型博客系统

## 1. 项目概述

实现一个基于 Flask + SQLAlchemy 的小型博客系统，支持文章管理、标签 CRUD、文章与标签的多对多关联，以及按标签筛选文章。

**约束条件**：
- `app.py` 已完成，不可修改
- `models.py` 已定义 Article、Tag 模型和 article_tags 关联表（经代码审查，当前实现已满足 README 功能需求，但 README 标注"需要完善"——实际代码中 Article 模型依赖 Flask-SQLAlchemy 默认表名 `article`，与 ForeignKey 一致，功能完整）
- 需要实现 `routes_article.py` 和 `routes_tag.py` 两个路由模块
- 各模块间接口（模型字段名、关联表名）必须保持一致

## 2. 功能需求

### 2.1 标签 CRUD（routes_tag.py）

| 接口 | 方法 | 描述 | 请求体 | 成功响应 | 错误响应 |
|------|------|------|--------|----------|----------|
| `/tags` | POST | 创建标签 | `{"name": str}` | 201: `{"status":"ok","data":{"id":int,"name":str}}` | 400: name 缺失/空; 409: 名称重复 |
| `/tags` | GET | 获取所有标签 | — | 200: `{"status":"ok","data":[{"id":int,"name":str},...]}` | — |
| `/tags/<id>` | PUT | 编辑标签名称 | `{"name": str}` | 200: `{"status":"ok","data":{"id":int,"name":str}}` | 404: 标签不存在; 400: name 缺失; 409: 名称重复 |
| `/tags/<id>` | DELETE | 删除标签 | — | 200: `{"status":"ok","data":{"message":"Tag deleted"}}` | 404: 标签不存在 |

**特殊行为**：删除标签时，必须级联删除 `article_tags` 关联表中的所有关联记录。

### 2.2 文章 CRUD + 标签绑定（routes_article.py）

| 接口 | 方法 | 描述 | 请求体/参数 | 成功响应 | 错误响应 |
|------|------|------|-------------|----------|----------|
| `/articles` | GET | 列出所有文章 | 可选: `?tag=<name>` 或 `?tag_id=<id>` | 200: `{"status":"ok","data":[{"id":int,"title":str,"body":str},...]}` | — |
| `/articles` | POST | 创建文章 | `{"title":str,"body":str}` | 201: `{"status":"ok","data":{"id":int,"title":str,"body":str}}` | 400: 缺少 title 或 body |
| `/articles/<id>` | GET | 获取单篇文章 | — | 200: `{"status":"ok","data":{"id":int,"title":str,"body":str}}` | 404: 文章不存在 |
| `/articles/<id>/tags` | POST | 绑定标签到文章 | `{"tag_ids":[int,...]}` | 200: `{"status":"ok","data":{"message":"Tags bound"}}` | 404: 文章不存在; 400: 标签不存在 |
| `/articles/<id>/tags` | GET | 获取文章的所有标签 | — | 200: `{"status":"ok","data":[{"id":int,"name":str},...]}` | 404: 文章不存在 |
| `/articles/<id>/tags/<tag_id>` | DELETE | 解除文章与标签的关联 | — | 200: `{"status":"ok","data":{"message":"Tag unbound"}}` | 404: 文章不存在 |

**标签筛选行为**：
- `GET /articles?tag=Python` — 按标签名称筛选，返回包含该标签的所有文章
- `GET /articles?tag_id=1` — 按标签 ID 筛选，返回包含该标签的所有文章
- 不传筛选参数时返回所有文章
- 无匹配结果时返回空列表 `[]`
- 同时传递 `tag` 和 `tag_id` 时，按 `tag` 参数优先处理（测试未覆盖此场景，但需明确定义）

## 3. 数据模型需求

### 3.1 Article 模型（已实现，经代码审查功能完整）
- `id`: Integer, Primary Key
- `title`: String(200), Non-null
- `body`: Text, Non-null
- `tags`: 关系属性，通过 `article_tags` 关联到 Tag

### 3.2 Tag 模型（已实现，经代码审查功能完整）
- `id`: Integer, Primary Key
- `name`: String(80), Unique, Non-null
- `articles`: 反向关系属性

### 3.3 article_tags 关联表（已实现，经代码审查功能完整）
- `article_id`: Integer, FK → article.id, Primary Key
- `tag_id`: Integer, FK → tag.id, Primary Key

## 4. 统一响应格式

所有接口返回 JSON，格式为：
- **成功**: `{"status": "ok", "data": ...}`
- **错误**: `{"status": "error", "message": "错误描述"}`

## 5. 验收标准

### AC-1: 所有 API 接口可正常调用
- 标签 CRUD 4 个接口全部可用
- 文章 CRUD 3 个接口全部可用
- 文章标签绑定/查询/解绑 3 个接口全部可用
- 按标签筛选 2 种方式均可用

### AC-2: 测试全部通过
- `tests/test_basic.py` 中所有测试用例通过（共 18 个测试：TestArticleCRUD 4个 + TestTagCRUD 6个 + TestArticleTagBinding 4个 + TestFilterArticlesByTag 4个）

### AC-3: 错误处理完备
- 缺少必填字段返回 400
- 资源不存在返回 404
- 名称重复返回 409
- 删除标签级联删除关联

### AC-4: README.md 文件无需修改
功能实现不要求更新 README.md 文档内容。Git diff 中 README.md 无变更。

## 6. 隐含需求（从测试文件提取）

通过分析 `test_basic.py`，提取以下隐含需求：

1. **创建文章返回 201 状态码**（`test_create_article` 断言 `status_code == 201`）
2. **创建标签返回 201 状态码**（`test_create_tag` 断言 `status_code == 201`）
3. **创建标签名称重复返回 409**（`test_create_tag_duplicate` 断言 `status_code == 409`）
4. **创建标签无名称返回 400**（`test_create_tag_no_name` 断言 `status_code == 400`，请求体为 `{}`）
5. **编辑标签返回 200**（`test_update_tag` 断言 `status_code == 200`）
6. **删除标签返回 200**（`test_delete_tag` 断言 `status_code == 200`）
7. **绑定标签返回 200**（`test_bind_tags_to_article` 断言 `status_code == 200`）
8. **解除标签返回 200**（`test_unbind_tag_from_article` 断言 `status_code == 200`）
9. **删除标签后关联自动清除**（`test_delete_tag_removes_bindings` 验证级联行为）
10. **筛选无匹配返回空列表**（`test_filter_no_match` 断言空列表而非 404）
11. **sample_article fixture** 直接使用 SQLAlchemy ORM 创建文章（不经过 API），路由需兼容

## 7. 边界条件说明

### 7.1 解绑不存在的关联
测试未覆盖"解绑一个从未绑定的 tag_id"场景。实现时应采用宽容策略：如果关联不存在，仍返回 200（幂等行为），而非报错。

### 7.2 同时传递 tag 和 tag_id
测试未覆盖此场景。定义优先级：`tag` 参数优先于 `tag_id` 参数。
