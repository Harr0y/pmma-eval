# 测试验证报告 — T2-1 小型博客系统

## 1. 测试执行结果

**全部 18/18 测试通过** ✅

| 测试类 | 测试数 | 通过 | 失败 |
|--------|--------|------|------|
| TestArticleCRUD | 4 | 4 | 0 |
| TestTagCRUD | 6 | 6 | 0 |
| TestArticleTagBinding | 4 | 4 | 0 |
| TestFilterArticlesByTag | 4 | 4 | 0 |
| **合计** | **18** | **18** | **0** |

### 逐条测试结果

| # | 测试用例 | 结果 |
|---|----------|------|
| 1 | test_create_article | PASSED |
| 2 | test_list_articles | PASSED |
| 3 | test_get_article | PASSED |
| 4 | test_create_article_missing_fields | PASSED |
| 5 | test_create_tag | PASSED |
| 6 | test_create_tag_duplicate | PASSED |
| 7 | test_create_tag_no_name | PASSED |
| 8 | test_list_tags | PASSED |
| 9 | test_update_tag | PASSED |
| 10 | test_delete_tag | PASSED |
| 11 | test_bind_tags_to_article | PASSED |
| 12 | test_get_article_tags | PASSED |
| 13 | test_unbind_tag_from_article | PASSED |
| 14 | test_delete_tag_removes_bindings | PASSED |
| 15 | test_filter_by_tag_name | PASSED |
| 16 | test_filter_by_tag_id | PASSED |
| 17 | test_filter_no_match | PASSED |
| 18 | test_no_filter_returns_all | PASSED |

## 2. 验收标准对照

### AC-1: 所有 API 接口可正常调用 ✅

| 接口 | 方法 | 验证结果 |
|------|------|----------|
| POST /tags | 创建标签 | 返回 201，含 id/name |
| GET /tags | 获取所有标签 | 返回 200，标签列表 |
| PUT /tags/<id> | 编辑标签名称 | 返回 200，更新后名称 |
| DELETE /tags/<id> | 删除标签 | 返回 200，级联删除关联 |
| POST /articles | 创建文章 | 返回 201，含 id/title/body |
| GET /articles | 列出所有文章 | 返回 200，文章列表 |
| GET /articles/<id> | 获取单篇文章 | 返回 200，文章详情 |
| POST /articles/<id>/tags | 绑定标签 | 返回 200，绑定成功 |
| GET /articles/<id>/tags | 获取文章标签 | 返回 200，标签列表 |
| DELETE /articles/<id>/tags/<tag_id> | 解除关联 | 返回 200，解绑成功 |
| GET /articles?tag=<name> | 按标签名称筛选 | 返回 200，筛选结果 |
| GET /articles?tag_id=<id> | 按标签 ID 筛选 | 返回 200，筛选结果 |

**全部 12 个接口正常工作。**

### AC-2: 测试全部通过 ✅

`tests/test_basic.py` 中 18 个测试用例全部通过。

### AC-3: 错误处理完备 ✅

| 错误场景 | 预期 | 实际 | 测试覆盖 |
|----------|------|------|----------|
| 创建文章缺少字段 | 400 | 400 | test_create_article_missing_fields |
| 创建标签 name 缺失 | 400 | 400 | test_create_tag_no_name |
| 创建标签名称重复 | 409 | 409 | test_create_tag_duplicate |
| 删除标签级联删除关联 | 关联清除 | 关联清除 | test_delete_tag_removes_bindings |
| 筛选无匹配 | 空列表 | 空列表 | test_filter_no_match |

### AC-4: README.md 未修改 ✅

Git diff 确认 README.md 无变更。

## 3. 修改的文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| starter/routes_tag.py | 新增实现 | 标签 CRUD 4 个路由 |
| starter/routes_article.py | 新增实现 | 文章路由 6 个 |
| starter/app.py | 未修改 | 按约束保持不变 |
| starter/models.py | 未修改 | 已有完整实现 |
| README.md | 未修改 | 按验收标准保持不变 |

## 4. 已知非阻塞问题

1. **SQLAlchemy LegacyAPIWarning**: 代码中 `Tag.query.get(id)` / `Article.query.get(id)` 在 SQLAlchemy 2.0 中已标记为废弃，建议未来迁移到 `db.session.get(Model, id)`。功能完全正确，不影响测试结果。

## 5. 总体评估

**符合交付标准。** 全部 18 个测试通过，4 项验收标准全部满足。
