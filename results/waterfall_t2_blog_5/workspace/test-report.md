# 测试验证报告 — T2-1 小型博客系统

## 1. 测试环境

- **测试框架**：pytest
- **测试命令**：`python -m pytest tests/ -v`
- **测试文件**：tests/test_basic.py
- **测试数据库**：SQLite 内存模式（:memory:）

## 2. 验收标准验证

### AC-1: 所有 API 接口可正常调用 — ✅ 通过

| # | 端点 | 方法 | 状态码 | 响应格式 |
|---|------|------|--------|----------|
| 1 | /articles | POST | 201 | {"status":"ok","data":{"id","title","body"}} |
| 2 | /articles | GET | 200 | {"status":"ok","data":[...]} |
| 3 | /articles/\<id\> | GET | 200/404 | {"status":"ok/error","data/message":...} |
| 4 | /articles/\<id\>/tags | POST | 200/404/400 | {"status":"ok/error","data/message":...} |
| 5 | /articles/\<id\>/tags | GET | 200/404 | {"status":"ok/error","data/message":...} |
| 6 | /articles/\<id\>/tags/\<tag_id\> | DELETE | 200/404 | {"status":"ok/error","data/message":...} |
| 7 | /tags | POST | 201/400/409 | {"status":"ok/error","data/message":...} |
| 8 | /tags | GET | 200 | {"status":"ok","data":[...]} |
| 9 | /tags/\<id\> | PUT | 200/404/400/409 | {"status":"ok/error","data/message":...} |
| 10 | /tags/\<id\> | DELETE | 200/404 | {"status":"ok/error","data/message":...} |

### AC-2: 所有 18 个测试用例通过 — ✅ 通过

**18/18 PASSED (100%)**

### AC-3: README.md 无需修改 — ✅ 通过

## 3. 测试用例详细结果

### TestArticleCRUD (4/4 PASS)

| 测试用例 | 验证需求 | 结果 |
|----------|---------|------|
| test_create_article | FR-ART-01 | PASS |
| test_list_articles | FR-ART-02 | PASS |
| test_get_article | FR-ART-03 | PASS |
| test_create_article_missing_fields | FR-ART-01 错误处理 | PASS |

### TestTagCRUD (6/6 PASS)

| 测试用例 | 验证需求 | 结果 |
|----------|---------|------|
| test_create_tag | FR-TAG-01 | PASS |
| test_create_tag_duplicate | FR-TAG-01 409 | PASS |
| test_create_tag_no_name | FR-TAG-01 400 | PASS |
| test_list_tags | FR-TAG-02 | PASS |
| test_update_tag | FR-TAG-03 | PASS |
| test_delete_tag | FR-TAG-04 | PASS |

### TestArticleTagBinding (4/4 PASS)

| 测试用例 | 验证需求 | 结果 |
|----------|---------|------|
| test_bind_tags_to_article | FR-ART-04 | PASS |
| test_get_article_tags | FR-ART-05 | PASS |
| test_unbind_tag_from_article | FR-ART-06 | PASS |
| test_delete_tag_removes_bindings | FR-TAG-04 级联 | PASS |

### TestFilterArticlesByTag (4/4 PASS)

| 测试用例 | 验证需求 | 结果 |
|----------|---------|------|
| test_filter_by_tag_name | FR-ART-02 tag 参数 | PASS |
| test_filter_by_tag_id | FR-ART-02 tag_id 参数 | PASS |
| test_filter_no_match | FR-ART-02 无匹配 | PASS |
| test_no_filter_returns_all | FR-ART-02 无参数 | PASS |

## 4. 边界条件验证

| 边界条件 | 结果 |
|----------|------|
| 绑定标签幂等性 | PASS — 重复绑定返回 200 |
| 解绑不存在的关联 | PASS — 幂等返回 200 |
| 空数据库 GET 请求 | PASS — 返回空列表 |
| 无效 tag_id 参数 | PASS — 返回空列表 |
| 纯空格 title/body/name | PASS — 返回 400 |
| 非字符串类型输入 | PASS — 返回 400 |
| 级联删除标签 | PASS — 关联自动清除 |

## 5. 已修复的问题

| 问题 | ATU | 修复内容 |
|------|-----|---------|
| Tag.query.get() 弃用警告 | ATU-003 | 替换为 db.session.get(Tag, id) |
| 空名检查缺少类型防御 | ATU-003 | 增加 isinstance(name, str) 检查 |
| 重复绑定标签返回 500 | ATU-004 | 增加 if tag not in article.tags 去重 |

## 6. 总体评估

**符合交付标准。** 18/18 测试通过，10/10 API 端点正常工作，3 条验收标准全部满足。
