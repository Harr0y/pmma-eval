# Requirements — T2-3 RBAC 权限管理系统

## 1. 概述

实现一个基于角色的访问控制（RBAC）系统，支持多租户隔离、角色继承和细粒度权限管理。系统基于 Flask，使用 JWT 认证，代码分布在 6 个模块文件中。

## 2. 已有模块（不可修改）

| 文件 | 职责 | 状态 |
|------|------|------|
| `app.py` | Flask 工厂、DB 初始化、Blueprint 注册 | ✅ 完成 |
| `models.py` | SQLAlchemy 模型定义（Tenant, User, Role, Permission, Document + 关联表） | ✅ 完成 |
| `middleware.py` | JWT 验证、权限检查装饰器、角色继承遍历 | ✅ 完成 |

## 3. 待实现模块

### 3.1 认证接口（routes_auth.py）

**FR-AUTH-1**: `POST /login` 用户登录
- 请求体：`{"username": str, "password": str}`
- 成功响应：`{"status": "ok", "data": {"token": str}}`，HTTP 200
- JWT payload 包含：`user_id`, `tenant_id`, `exp`
- 密码验证使用 `middleware.hash_password()`
- 错误场景：
  - 缺少 username 或 password → HTTP 400
  - 用户不存在或密码错误 → HTTP 401

### 3.2 文档接口（routes_document.py）

**FR-DOC-1**: `GET /documents` 列出当前租户文档
- 权限要求：`doc.read`
- 仅返回当前用户所属 tenant 的文档
- 响应：`{"status": "ok", "data": [{id, tenant_id, owner_id, title, content}, ...]}`

**FR-DOC-2**: `GET /documents/<id>` 获取单个文档
- 权限要求：`doc.read`
- 必须属于同一 tenant，否则返回 404
- 响应同上

**FR-DOC-3**: `POST /documents` 创建文档
- 权限要求：`doc.write`
- 请求体：`{"title": str, "content": str}`
- `tenant_id` 从 JWT 获取，`owner_id` 为当前用户
- 成功响应：HTTP 201

**FR-DOC-4**: `PUT /documents/<id>` 更新文档
- 权限要求：`doc.write` +（是 owner 或拥有 `doc.write.any` 权限）
- 请求体：`{"title": str, "content": str}`
- 必须属于同一 tenant
- 错误：404（不存在或不同 tenant），403（非 owner 且无 write.any）

**FR-DOC-5**: `DELETE /documents/<id>` 删除文档
- 权限要求：`doc.delete`
- 必须属于同一 tenant
- 错误：404（不存在或不同 tenant）

### 3.3 角色管理接口（routes_role.py）

**FR-ROLE-1**: `POST /roles` 创建角色
- 权限要求：`role.manage`
- 请求体：`{"name": str, "parent_role_id": int|null, "permissions": [str, ...]}`
- `parent_role_id` 必须属于同一 tenant
- 同一 tenant 内角色名不可重复
- 成功响应：HTTP 201
- 错误：400（name 缺失或 parent 无效），409（角色名重复）

**FR-ROLE-2**: `GET /roles` 列出本 tenant 角色
- 权限要求：`role.manage`
- 响应：`{"status": "ok", "data": [...]}`

**FR-ROLE-3**: `PUT /roles/<id>/permissions` 更新角色权限和父角色
- 权限要求：`role.manage`
- 请求体：`{"permissions": [str, ...], "parent_role_id": int|null}`
- **必须检测继承链循环**（设置 parent_role_id 时）
- 错误：404（角色不存在），400（循环检测或 parent 无效）

**FR-ROLE-4**: `POST /users/<id>/roles` 分配角色给用户
- 权限要求：`role.manage`
- 请求体：`{"role_id": int}`
- 用户和角色必须属于同一 tenant
- 错误：404（用户或角色不存在）

**FR-ROLE-5**: `DELETE /users/<id>/roles/<role_id>` 移除用户角色
- 权限要求：`role.manage`
- 幂等操作：角色未分配时不报错
- 错误：404（用户不存在）

## 4. 非功能需求

**NFR-1**: 多租户隔离 — 所有数据操作必须限制在当前用户的 tenant 范围内
**NFR-2**: 角色继承 — 权限检查必须沿 `parent_role_id` 链向上遍历（已由 middleware.py 实现）
**NFR-3**: 继承链循环检测 — 设置 parent_role_id 时必须检测是否形成环
**NFR-4**: 接口一致性 — 所有接口返回格式统一为 `{"status": "ok/error", "data/message": ...}`

## 5. 模块间接口约定

- 权限码字符串：`doc.read`, `doc.write`, `doc.delete`, `doc.write.any`, `role.manage`
- JWT payload 结构：`{"user_id": int, "tenant_id": int, "exp": timestamp}`
- Blueprint 名称：`auth_bp`, `document_bp`, `role_bp`
- 认证/权限检查：使用 `middleware.check_permission(code)` 装饰器
- 获取当前用户：使用 `middleware.get_current_user()` 辅助函数

## 6. 验收标准

| # | 验收标准 | 验证方式 |
|---|---------|---------|
| AC-1 | `POST /login` 返回有效 JWT | test_basic.py TestAuth |
| AC-2 | 缺失/无效/过期 token 返回 401 | test_basic.py TestAuth |
| AC-3 | 管理员可创建角色 | test_basic.py TestRoleManagement |
| AC-4 | 非管理员无法创建角色（403） | test_basic.py TestRoleManagement |
| AC-5 | 子角色继承父角色权限 | test_basic.py TestRoleManagement |
| AC-6 | 继承链循环被拒绝（400） | test_basic.py TestRoleManagement |
| AC-7 | viewer 可读不可写 | test_basic.py TestDocumentRBAC |
| AC-8 | editor 可编辑自己的文档 | test_basic.py TestDocumentRBAC |
| AC-9 | editor 不可编辑他人文档（403） | test_basic.py TestDocumentRBAC |
| AC-10 | admin 拥有 write.any 可编辑任意文档 | test_basic.py TestDocumentRBAC |
| AC-11 | 无权限用户访问文档返回 403 | test_basic.py TestDocumentRBAC |
| AC-12 | 跨租户访问文档返回 404 | test_basic.py TestMultiTenant |
| AC-13 | 跨租户分配角色被拒绝（403/404） | test_basic.py TestMultiTenant |
| AC-14 | 文档列表仅显示本租户文档 | test_basic.py TestMultiTenant |
| AC-15 | 父角色权限变更传播到子角色 | test_basic.py TestPermissionInheritance |
| AC-16 | 父角色权限移除导致子角色失去权限 | test_basic.py TestPermissionInheritance |
| AC-17 | 多角色权限取并集 | test_basic.py TestPermissionInheritance |
