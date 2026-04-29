# 测试报告 — T2-1 小型博客系统

## 1. 测试概要

| 项目 | 结果 |
|------|------|
| 测试框架 | pytest |
| 测试文件 | tests/test_basic.py |
| 测试用例总数 | 18 |
| 通过 | 18 |
| 失败 | 0 |
| 通过率 | 100% |
| 执行时间 | ~0.31s |

**注意**：README.md 验收标准第 2 条提到"tests/test_basic.py 中的所有测试用例通过"，原始描述中写"16 个测试用例"，但实际 test_basic.py 中包含 **18 个测试方法**（TestArticleCRUD 4个 + TestTagCRUD 6个 + TestArticleTagBinding 4个 + TestFilterArticlesByTag 4个）。本报告以实际代码为准。

## 2. 测试执行结果

```
tests/test_basic.py::TestArticleCRUD::test_create_article PASSED
tests/test_basic.py::TestArticleCRUD::test_list_articles PASSED
tests/test_basic.py::TestArticleCRUD::test_get_article PASSED
tests/test_basic.py::TestArticleCRUD::test_create_article_missing_fields PASSED
tests/test_basic.py::TestTagCRUD::test_create_tag PASSED
tests/test_basic.py::TestTagCRUD::test_create_tag_duplicate PASSED
tests/test_basic.py::TestTagCRUD::test_create_tag_no_name PASSED
tests/test_basic.py::TestTagCRUD::test_list_tags PASSED
tests/test_basic.py::TestTagCRUD::test_update_tag PASSED
tests/test_basic.py::TestTagCRUD::test_delete_tag PASSED
tests/test_basic.py::TestArticleTagBinding::test_bind_tags_to_article PASSED
tests/test_basic.py::TestArticleTagBinding::test_get_article_tags PASSED
tests/test_basic.py::TestArticleTagBinding::test_unbind_tag_from_article PASSED
tests/test_basic.py::TestArticleTagBinding::test_delete_tag_removes_bindings PASSED
tests/test_basic.py::TestFilterArticlesByTag::test_filter_by_tag_name PASSED
tests/test_basic.py::TestFilterArticlesByTag::test_filter_by_tag_id PASSED
tests/test_basic.py::TestFilterArticlesByTag::test_filter_no_match PASSED
tests/test_basic.py::TestFilterArticlesByTag::test_no_filter_returns_all PASSED
```

## 3. 验收标准验证

### 3.1 功能验收标准

| AC# | 验收项 | 测试用例 | 结果 |
|-----|--------|----------|------|
| AC-1 | 10 个 API 端点可正常调用 | 代码审查（见下方端点清单） | ✅ 通过 |
| AC-2 | 创建文章成功，返回 201 | test_create_article | ✅ 通过 |
| AC-3 | 列出所有文章 | test_list_articles | ✅ 通过 |
| AC-4 | 获取单篇文章成功 | test_get_article | ✅ 通过 |
| AC-5 | 缺少字段返回 400 | test_create_article_missing_fields | ✅ 通过 |
| AC-6 | 创建标签成功，返回 201 | test_create_tag | ✅ 通过 |
| AC-7 | 重复标签返回 409 | test_create_tag_duplicate | ✅ 通过 |
| AC-8 | name 为空返回 400 | test_create_tag_no_name | ✅ 通过 |
| AC-9 | 获取标签列表 | test_list_tags | ✅ 通过 |
| AC-10 | 编辑标签名称 | test_update_tag | ✅ 通过 |
| AC-11 | 删除标签 | test_delete_tag | ✅ 通过 |
| AC-12 | 绑定标签成功 | test_bind_tags_to_article | ✅ 通过 |
| AC-13 | 获取文章标签 | test_get_article_tags | ✅ 通过 |
| AC-14 | 解除关联成功 | test_unbind_tag_from_article | ✅ 通过 |
| AC-15 | 删除标签级联解除关联 | test_delete_tag_removes_bindings | ✅ 通过 |
| AC-16 | 按标签名筛选文章 | test_filter_by_tag_name | ✅ 通过 |
| AC-17 | 按标签 ID 筛选文章 | test_filter_by_tag_id | ✅ 通过 |
| AC-18 | 筛选无匹配返回空列表 | test_filter_no_match | ✅ 通过 |
| AC-19 | 不传筛选返回所有文章 | test_no_filter_returns_all | ✅ 通过 |
| AC-20 | 全部测试用例通过 | 18/18 passed | ✅ 通过 |

#### AC-1 端点清单（10 个 API 端点）

| # | 端点 | 方法 | 实现文件 | 注册方式 |
|---|------|------|----------|----------|
| 1 | `/tags` | POST | routes_tag.py | `@tag_bp.route('/tags', methods=['POST'])` |
| 2 | `/tags` | GET | routes_tag.py | `@tag_bp.route('/tags', methods=['GET'])` |
| 3 | `/tags/<id>` | PUT | routes_tag.py | `@tag_bp.route('/tags/<int:id>', methods=['PUT'])` |
| 4 | `/tags/<id>` | DELETE | routes_tag.py | `@tag_bp.route('/tags/<int:id>', methods=['DELETE'])` |
| 5 | `/articles` | GET | routes_article.py | `@article_bp.route('/articles', methods=['GET'])` |
| 6 | `/articles` | POST | routes_article.py | `@article_bp.route('/articles', methods=['POST'])` |
| 7 | `/articles/<id>` | GET | routes_article.py | `@article_bp.route('/articles/<int:id>', methods=['GET'])` |
| 8 | `/articles/<id>/tags` | POST | routes_article.py | `@article_bp.route('/articles/<int:id>/tags', methods=['POST'])` |
| 9 | `/articles/<id>/tags` | GET | routes_article.py | `@article_bp.route('/articles/<int:id>/tags', methods=['GET'])` |
| 10 | `/articles/<id>/tags/<tag_id>` | DELETE | routes_article.py | `@article_bp.route('/articles/<int:id>/tags/<int:tag_id>', methods=['DELETE'])` |

所有 10 个端点均已在 app.py 中通过 `app.register_blueprint()` 注册。

### 3.2 隐含需求验证

| IR# | 隐含需求 | 验证方式 | 结果 | 备注 |
|-----|----------|----------|------|------|
| IR-1 | models.py 无需修改 | 代码审查 | ✅ 满足 | 模型定义完整，字段与需求一致 |
| IR-2 | 路由文件正确导入 models | import 验证 | ✅ 满足 | 两个路由文件均 `from models import ...` |
| IR-3 | Blueprint 名称正确 | app.py 注册验证 | ✅ 满足 | `article_bp` / `tag_bp` 与 app.py 一致 |
| IR-4 | 删除标签级联删除关联 | test_delete_tag_removes_bindings | ✅ 满足 | 自动化测试验证 |
| IR-5 | 筛选参数可选 | test_no_filter_returns_all | ✅ 满足 | 自动化测试验证 |
| IR-6 | 无匹配返回空列表 | test_filter_no_match | ✅ 满足 | 自动化测试验证 |
| IR-7 | 绑定标签处理不存在 tag_id | 代码审查 | ⚠️ 部分满足 | 代码实现正确（routes_article.py 第 99-101 行返回 400），但 test_basic.py 中缺少对应的自动化测试用例（详见第 5 节） |
| IR-8 | 空字符串 name 处理 | 代码审查 | ⚠️ 部分满足 | 代码实现正确（routes_tag.py 第 41 行 `not name.strip()` 处理空字符串和纯空格），但测试仅覆盖 `json={}` 场景，未覆盖 `{"name": ""}` 和 `{"name": "   "}`（详见第 5 节） |

## 4. 测试覆盖分析

### 4.1 按模块覆盖

| 模块 | 测试类 | 测试数 | 覆盖端点 |
|------|--------|--------|----------|
| 文章 CRUD | TestArticleCRUD | 4 | GET /articles, POST /articles, GET /articles/\<id\> |
| 标签 CRUD | TestTagCRUD | 6 | POST /tags, GET /tags, PUT /tags/\<id\>, DELETE /tags/\<id\> |
| 文章标签绑定 | TestArticleTagBinding | 4 | POST /articles/\<id\>/tags, GET /articles/\<id\>/tags, DELETE /articles/\<id\>/tags/\<tag_id\>, DELETE /tags/\<id\>（级联） |
| 标签筛选 | TestFilterArticlesByTag | 4 | GET /articles?tag=\<name\>, GET /articles?tag_id=\<id\> |

### 4.2 按测试类型覆盖

| 类型 | 测试数 | 描述 |
|------|--------|------|
| 正常流程 | 10 | 创建、查询、绑定、筛选 |
| 错误处理 | 4 | 400 缺失字段、400 name 为空、409 重复标签、400 不存在 tag_id（间接） |
| 边界条件 | 4 | 重复绑定、空结果、无筛选、级联删除 |

## 5. 测试覆盖缺口

以下错误场景在 requirements.md 中定义，但 test_basic.py（任务提供的测试文件）中**缺少对应的自动化测试用例**：

| 端点 | 错误场景 | 预期状态码 | 有测试？ | 代码实现 |
|------|----------|-----------|----------|----------|
| GET /articles/\<id\> | 文章不存在 | 404 | ❌ 无 | ✅ 已实现 |
| PUT /tags/\<id\> | 标签不存在 | 404 | ❌ 无 | ✅ 已实现 |
| PUT /tags/\<id\> | 新 name 与已有标签重名 | 409 | ❌ 无 | ✅ 已实现 |
| DELETE /tags/\<id\> | 标签不存在 | 404 | ❌ 无 | ✅ 已实现 |
| POST /articles/\<id\>/tags | 文章不存在 | 404 | ❌ 无 | ✅ 已实现 |
| POST /articles/\<id\>/tags | tag_id 不存在 | 400 | ❌ 无 | ✅ 已实现 |
| GET /articles/\<id\>/tags | 文章不存在 | 404 | ❌ 无 | ✅ 已实现 |
| DELETE /articles/\<id\>/tags/\<tag_id\> | 文章不存在 | 404 | ❌ 无 | ✅ 已实现 |
| POST /tags | name 为空字符串 `""` | 400 | ❌ 无 | ✅ 已实现 |
| POST /tags | name 为纯空格 `"  "` | 400 | ❌ 无 | ✅ 已实现 |

**说明**：test_basic.py 为任务提供的测试文件，本项目未修改该文件。上述缺失的测试场景通过代码审查确认实现正确（routes_tag.py 和 routes_article.py 中均包含对应的错误处理逻辑），但缺少自动化回归测试保护。

## 6. 已知技术债务

| 项目 | 严重程度 | 描述 |
|------|----------|------|
| SQLAlchemy LegacyAPIWarning | 低 | `Query.get()` 在 SQLAlchemy 2.0 中废弃，建议迁移到 `db.session.get()`。不影响功能正确性。共产生 22 条警告。 |
| 非 JSON 请求防护 | 低 | `POST /articles` 和 `POST /articles/<id>/tags` 未对 `request.get_json()` 返回 None 做防护。`routes_tag.py` 已做防护（`data.get('name') if data else None`），但 `routes_article.py` 未做。测试场景均使用 JSON 请求，不影响当前功能。 |
| models.py 循环导入 | 低 | models.py 第 16 行 `from app import db`，app.py 第 23 行 `from models import Article, Tag`，存在双向依赖。当前通过 `sys.path.insert(0, ...)` 和 Flask app context 机制规避，测试中未暴露问题。 |
| 测试覆盖缺口 | 中 | 10 个错误/边界场景缺少自动化测试用例（见第 5 节）。代码实现正确但缺少回归保护。 |

## 7. 总体评估

**符合交付标准。** 全部 18 个测试用例通过（100%），20 条验收标准全部满足，8 条隐含需求中 6 条完全满足、2 条部分满足（代码实现正确但缺少自动化测试）。实现与 requirements.md 和 design.md 完全一致。test_basic.py 为任务提供的原始测试文件，所有提供的测试用例均通过。
