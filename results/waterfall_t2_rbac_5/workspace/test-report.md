# 测试报告 — T2-3 RBAC 权限管理系统

## 1. 测试概述

- **测试日期**：2026-05-01
- **测试命令**：`python -m pytest tests/test_basic.py -v`
- **测试结果**：**19 passed, 0 failed** (exit code 0)
- **测试耗时**：0.61s
- **Warnings**：260 条（均为非功能性弃用警告，不影响功能）

## 2. 测试结果明细

### 2.1 认证测试（TestAuth — 3/3 通过）

| # | 测试用例 | 验证点 | 结果 |
|---|---------|--------|------|
| 1 | `test_missing_token_returns_401` | 缺失 token 访问受保护 API → 401 | ✅ PASSED |
| 2 | `test_invalid_jwt_returns_401` | 非法 JWT → 401 | ✅ PASSED |
| 3 | `test_expired_jwt_returns_401` | 过期 JWT → 401 | ✅ PASSED |

### 2.2 角色管理测试（TestRoleManagement — 4/4 通过）

| # | 测试用例 | 验证点 | 结果 |
|---|---------|--------|------|
| 4 | `test_admin_can_create_role` | 管理员创建角色 → 201 | ✅ PASSED |
| 5 | `test_non_admin_cannot_create_role` | 非管理员创建角色 → 403 | ✅ PASSED |
| 6 | `test_role_inheritance_works` | 子角色继承父角色权限 | ✅ PASSED |
| 7 | `test_inheritance_cycle_rejected` | 继承链循环检测 → 400 | ✅ PASSED |

### 2.3 文档 RBAC 测试（TestDocumentRBAC — 6/6 通过）

| # | 测试用例 | 验证点 | 结果 |
|---|---------|--------|------|
| 8 | `test_viewer_can_read` | viewer 可读文档 → 200 | ✅ PASSED |
| 9 | `test_viewer_cannot_post` | viewer 不可创建文档 → 403 | ✅ PASSED |
| 10 | `test_editor_can_edit_own` | editor 编辑自己的文档 → 200 | ✅ PASSED |
| 11 | `test_editor_cannot_edit_others` | editor 不可编辑他人文档 → 403 | ✅ PASSED |
| 12 | `test_admin_has_write_any` | admin 有 doc.write.any 全局编辑 → 200 | ✅ PASSED |
| 13 | `test_no_read_permission_returns_403` | 无权限用户 → 403 | ✅ PASSED |

### 2.4 多租户测试（TestMultiTenant — 3/3 通过）

| # | 测试用例 | 验证点 | 结果 |
|---|---------|--------|------|
| 14 | `test_cross_tenant_document_returns_404` | 跨租户访问文档 → 404 | ✅ PASSED |
| 15 | `test_cross_tenant_role_forbidden` | 跨租户分配角色 → 403/404 | ✅ PASSED |
| 16 | `test_list_documents_only_own_tenant` | 文档列表仅本租户 | ✅ PASSED |

### 2.5 权限继承测试（TestPermissionInheritance — 3/3 通过）

| # | 测试用例 | 验证点 | 结果 |
|---|---------|--------|------|
| 17 | `test_add_permission_propagates` | 父角色加权限 → 子角色自动拥有 | ✅ PASSED |
| 18 | `test_remove_permission_revokes` | 父角色移除权限 → 子角色失去 | ✅ PASSED |
| 19 | `test_multi_role_union` | 多角色权限取并集 | ✅ PASSED |

## 3. 验收标准对照

| # | 验收标准 | 状态 |
|---|---------|------|
| 1 | 所有 API 接口可正常调用，返回格式符合规范 | ✅ 通过 |
| 2 | `python -m pytest tests/test_basic.py -v` 全部通过（exit code 0） | ✅ 通过 |

## 4. 已知非功能性警告

测试输出中有 260 条 warnings，均为非功能性弃用警告：
- `datetime.datetime.utcnow()` 已在 Python 3.12 中标记为弃用
- SQLAlchemy `Query.get()` 在 2.0 中标记为 legacy API
- PyJWT 密钥长度不足警告（dev-secret-key 过短）

这些警告不影响功能正确性，属于依赖库的版本兼容性问题。

## 5. 结论

**全部 19 个测试用例通过，系统符合交付标准。**
