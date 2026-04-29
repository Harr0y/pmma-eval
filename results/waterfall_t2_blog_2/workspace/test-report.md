# 测试验证报告 — T2-1 小型博客系统

## 1. 测试执行概要

| 指标 | 数值 |
|------|------|
| 测试框架 | pytest |
| 测试文件 | tests/test_basic.py |
| 总测试数 | 18 |
| 通过 | 18 |
| 失败 | 0 |
| 通过率 | **100%** |
| 执行时间 | 0.31s |
| 结论 | **符合交付标准** |

## 2. 测试执行输出

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

======================= 18 passed, 23 warnings in 0.31s ========================
```

## 3. 逐条验收结果

| AC | 验收标准 | 对应测试 | 结果 |
|----|----------|----------|------|
| AC-01 | POST /articles 正常创建文章 | test_create_article | ✅ PASS |
| AC-02 | GET /articles 返回所有文章 | test_list_articles | ✅ PASS |
| AC-03 | GET /articles/\<id\> 返回单篇文章 | test_get_article | ✅ PASS |
| AC-04 | 缺少 body 时返回 400 | test_create_article_missing_fields | ✅ PASS |
| AC-05 | POST /tags 创建标签返回 201 | test_create_tag | ✅ PASS |
| AC-06 | 重复标签名返回 409 | test_create_tag_duplicate | ✅ PASS |
| AC-07 | 缺少 name 时返回 400 | test_create_tag_no_name | ✅ PASS |
| AC-08 | GET /tags 返回所有标签 | test_list_tags | ✅ PASS |
| AC-09 | PUT /tags/\<id\> 编辑标签名 | test_update_tag | ✅ PASS |
| AC-10 | DELETE /tags/\<id\> 删除标签 | test_delete_tag | ✅ PASS |
| AC-11 | POST /articles/\<id\>/tags 绑定标签 | test_bind_tags_to_article | ✅ PASS |
| AC-12 | GET /articles/\<id\>/tags 获取文章标签 | test_get_article_tags | ✅ PASS |
| AC-13 | DELETE /articles/\<id\>/tags/\<tag_id\> 解除绑定 | test_unbind_tag_from_article | ✅ PASS |
| AC-14 | 删除标签时级联解除关联 | test_delete_tag_removes_bindings | ✅ PASS |
| AC-15 | GET /articles?tag=Python 按标签名筛选 | test_filter_by_tag_name | ✅ PASS |
| AC-16 | GET /articles?tag_id=\<id\> 按标签 ID 筛选 | test_filter_by_tag_id | ✅ PASS |
| AC-17 | 筛选无匹配返回空列表 | test_filter_no_match | ✅ PASS |
| AC-18 | 不传筛选参数返回所有文章 | test_no_filter_returns_all | ✅ PASS |
| AC-19 | tests/test_basic.py 全部通过 | pytest 全量运行 | ✅ PASS (18/18) |

## 4. 非阻塞性警告

- **SQLAlchemy LegacyAPIWarning**（23 个）：`Model.query.get()` 在 SQLAlchemy 2.0 中已标记为 legacy。建议后续迭代中替换为 `db.session.get(Model, id)`。不影响功能正确性。

## 5. 结论

**AC-01 至 AC-19 共 19 项验收标准全部通过，18 个测试用例 100% PASSED。项目满足交付标准。**
