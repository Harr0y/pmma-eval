# Test Report — T2-3 RBAC 权限管理系统

## 1. 测试执行概要

| 指标 | 值 |
|------|------|
| 测试总数 | 19 |
| 通过 | 19 |
| 失败 | 0 |
| 执行时间 | ~0.5s |

## 2. 验收标准验证结果

| # | 验收标准 | 对应测试 | 结果 |
|---|---------|---------|------|
| AC-1 | POST /login 返回有效 JWT | _login() fixture（所有测试间接验证） | ✅ PASS |
| AC-2 | 缺失/无效/过期 token 返回 401 | TestAuth (3 tests) | ✅ PASS |
| AC-3 | 管理员可创建角色 | test_admin_can_create_role | ✅ PASS |
| AC-4 | 非管理员无法创建角色 (403) | test_non_admin_cannot_create_role | ✅ PASS |
| AC-5 | 子角色继承父角色权限 | test_role_inheritance_works | ✅ PASS |
| AC-6 | 继承链循环被拒绝 (400) | test_inheritance_cycle_rejected | ✅ PASS |
| AC-7 | viewer 可读不可写 | test_viewer_can_read + test_viewer_cannot_post | ✅ PASS |
| AC-8 | editor 可编辑自己的文档 | test_editor_can_edit_own | ✅ PASS |
| AC-9 | editor 不可编辑他人文档 (403) | test_editor_cannot_edit_others | ✅ PASS |
| AC-10 | admin 拥有 write.any 可编辑任意文档 | test_admin_has_write_any | ✅ PASS |
| AC-11 | 无权限用户访问文档返回 403 | test_no_read_permission_returns_403 | ✅ PASS |
| AC-12 | 跨租户访问文档返回 404 | test_cross_tenant_document_returns_404 | ✅ PASS |
| AC-13 | 跨租户分配角色被拒绝 (403/404) | test_cross_tenant_role_forbidden | ✅ PASS |
| AC-14 | 文档列表仅显示本租户文档 | test_list_documents_only_own_tenant | ✅ PASS |
| AC-15 | 父角色权限变更传播到子角色 | test_add_permission_propagates | ✅ PASS |
| AC-16 | 父角色权限移除导致子角色失去权限 | test_remove_permission_revokes | ✅ PASS |
| AC-17 | 多角色权限取并集 | test_multi_role_union | ✅ PASS |

## 3. 测试覆盖分析

### 完全覆盖的功能需求

| 功能需求 | 覆盖测试 |
|---------|---------|
| FR-AUTH-1 POST /login | _login fixture + TestAuth |
| FR-DOC-1 GET /documents | AC-7, AC-11, AC-14 |
| FR-DOC-2 GET /documents/\<id\> | AC-12 |
| FR-DOC-3 POST /documents | AC-7, AC-8, AC-14 |
| FR-DOC-4 PUT /documents/\<id\> | AC-8, AC-9, AC-10 |
| FR-ROLE-1 POST /roles | AC-3, AC-4 |
| FR-ROLE-2 GET /roles | 间接验证（多个测试使用） |
| FR-ROLE-3 PUT /roles/\<id\>/permissions | AC-6, AC-15, AC-16 |
| FR-ROLE-4 POST /users/\<id\>/roles | AC-5, AC-13, AC-17 |
| FR-ROLE-5 DELETE /users/\<id\>/roles/\<role_id\> | 间接验证（测试中角色分配/移除流程） |

### 部分覆盖（非阻塞）

- **FR-DOC-5 DELETE /documents/\<id\>**: 代码实现完整（含 tenant 隔离），但无直接测试用例
- **FR-ROLE-5 DELETE /users/\<id\>/roles/\<role_id\>**: 代码实现完整（含幂等处理），但无直接测试用例

### 非功能需求验证

| NFR | 状态 | 验证依据 |
|-----|------|---------|
| NFR-1 多租户隔离 | ✅ | AC-12, AC-13, AC-14 |
| NFR-2 角色继承 | ✅ | AC-5, AC-15, AC-16 |
| NFR-3 循环检测 | ✅ | AC-6 |
| NFR-4 接口一致性 | ✅ | 所有测试验证返回格式 |

## 4. 已知问题（非阻塞）

1. `test_basic.py:116` 使用已弃用的 `datetime.datetime.utcnow()`
2. `models.py` / `middleware.py` 中使用已弃用的 `Query.get()`
3. 测试中 JWT 密钥过短（11 bytes），仅影响测试环境
4. DELETE 端点和 409 错误场景缺少直接测试用例

## 5. 结论

**符合交付标准。** 17 条验收标准全部通过，19/19 测试通过。
