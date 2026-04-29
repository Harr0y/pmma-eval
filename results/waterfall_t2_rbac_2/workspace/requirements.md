# RBAC 权限管理系统 — 需求分析文档

## 1. 项目概述

实现一个多模块 RBAC（基于角色的访问控制）权限管理系统，支持多租户隔离、角色继承、文档 CRUD 权限控制。系统基于 Flask 框架，使用 JWT 进行认证。

## 2. 功能需求

### 2.1 数据模型

| 模型 | 字段 | 约束 |
|------|------|------|
| Tenant | id, name | name NOT NULL |
| User | id, tenant_id, username, password_hash, created_at | username UNIQUE, tenant_id FK→tenant.id, created_at 默认当前时间 |
| Role | id, tenant_id, name, parent_role_id | tenant_id FK→tenant.id, parent_role_id FK→role.id (nullable, 自引用) |
| Permission | id, code | code UNIQUE, 取值: `doc.read`, `doc.write`, `doc.delete`, `doc.write.any`, `role.manage` |
| Document | id, tenant_id, owner_id, title, content | tenant_id FK→tenant.id, owner_id FK→user.id, title NOT NULL, content 默认空字符串 |
| role_permissions | role_id, permission_id | 多对多关联表 |
| user_roles | user_id, role_id | 多对多关联表 |

### 2.2 认证中间件（middleware.py — 已实现，不可修改）

middleware.py 提供以下公开接口，各路由模块必须通过这些接口进行认证和权限检查：

| 函数/装饰器 | 签名 | 用途 |
|-------------|------|------|
| `hash_password()` | `hash_password(password: str) -> str` | SHA-256 密码哈希，位于 middleware.py |
| `decode_token()` | `decode_token(token: str) -> dict \| None` | 解码验证 JWT，位于 middleware.py |
| `get_current_user()` | `get_current_user() -> (User, error_response)` | 从 JWT 提取当前用户，返回 (user, None) 或 (None, error_response) |
| `get_user_permissions()` | `get_user_permissions(user: User) -> Set[str]` | 获取用户所有权限（含继承），返回权限码集合 |
| `check_permission()` | `@check_permission(permission_code: str)` 装饰器，检查当前用户是否拥有指定权限 |
| `require_auth` | `@require_auth` 装饰器，仅验证 JWT 身份，不检查具体权限 |

核心行为：
- JWT 从 `Authorization: Bearer <token>` 头部解析
- 缺失/无效/过期 token → 返回 401
- 权限检查沿 `parent_role_id` 继承链向上递归查找（通过 `_collect_role_permissions` 实现）
- JWT payload 包含: `user_id`, `tenant_id`, `exp`
- JWT secret 从 `app.config['JWT_SECRET']` 获取，过期时间从 `app.config['JWT_EXPIRY_HOURS']` 获取

### 2.3 认证接口（routes_auth.py）

**POST /login**
- 请求体: `{"username": str, "password": str}`
- 成功响应 (200): `{"status": "ok", "data": {"token": str}}`
- 错误响应:
  - 400: username 或 password 缺失
  - 401: 用户名不存在或密码错误（**统一返回 401，不区分两种情况，防止用户名枚举攻击**）

### 2.4 文档接口（routes_document.py）

**GET /documents**
- 权限: `doc.read`（缺少权限返回 403）
- 仅返回当前用户 tenant 的文档
- 成功响应 (200): `{"status": "ok", "data": [{id, tenant_id, owner_id, title, content}, ...]}`

**GET /documents/<id>**
- 权限: `doc.read`（缺少权限返回 403）
- 仅限同 tenant 文档，否则返回 404
- 成功响应 (200): `{"status": "ok", "data": {id, tenant_id, owner_id, title, content}}`

**POST /documents**
- 权限: `doc.write`（缺少权限返回 403）
- 请求体: `{"title": str, "content": str}`
- tenant_id 从 JWT 获取，owner_id 为当前用户
- 成功响应 (201): `{"status": "ok", "data": {id, tenant_id, owner_id, title, content}}`

**PUT /documents/<id>**
- 权限: `doc.write`（缺少返回 403）+ 额外 owner 检查
- 仅限同 tenant，否则返回 404
- 非当前文档 owner 且无 `doc.write.any` 权限 → 返回 403
- 请求体: `{"title": str, "content": str}`
- 成功响应 (200): `{"status": "ok", "data": {id, tenant_id, owner_id, title, content}}`

**DELETE /documents/<id>**
- 权限: `doc.delete`（缺少权限返回 403）
- 仅限同 tenant，否则返回 404
- **不要求 owner 检查**：拥有 `doc.delete` 权限的用户可删除同 tenant 内任意文档
- 成功响应 (200): `{"status": "ok", "data": ...}`

### 2.5 角色管理接口（routes_role.py）

**POST /roles** — 创建角色
- 权限: `role.manage`（缺少权限返回 403）
- 请求体: `{"name": str, "parent_role_id": int|null, "permissions": [str, ...]}`
- 成功响应 (201): `{"status": "ok", "data": {id, name, parent_role_id, permissions: [str, ...]}}`
- 错误: 400 name 缺失或 parent 无效; 409 同 tenant 内角色名重复

**GET /roles** — 列出本 tenant 角色
- 权限: `role.manage`（缺少权限返回 403）
- 成功响应 (200): `{"status": "ok", "data": [{id: int, name: str, parent_role_id: int|null, permissions: [str, ...]}, ...]}`

**PUT /roles/<id>/permissions** — 更新角色权限和/或父角色
- 权限: `role.manage`（缺少权限返回 403）
- 请求体: `{"permissions": [str, ...], "parent_role_id": int|null}`
- **`permissions` 字段为全量替换语义**：提交的新列表完全替换旧权限集，不是追加
- 必须检测继承链循环（设置 parent_role_id 时）
- 错误: 404 角色不存在; 400 循环检测或 parent 无效

**POST /users/<id>/roles** — 分配角色
- 权限: `role.manage`（缺少权限返回 403）
- 请求体: `{"role_id": int}`
- user 和 role 必须属于同 tenant
- 错误: 404 user 或 role 不存在

**DELETE /users/<id>/roles/<role_id>** — 移除角色
- 权限: `role.manage`（缺少权限返回 403）
- 幂等操作 — 角色未分配时不报错
- 错误: 404 user 不存在

### 2.6 接口返回格式规范

所有接口统一使用以下格式：
- 成功: `{"status": "ok", "data": ...}`
- 错误: `{"status": "error", "message": "错误描述"}`

### 2.7 统一错误码策略

| 场景 | HTTP 状态码 | 说明 |
|------|-------------|------|
| 认证失败（token 缺失/无效/过期） | 401 | Unauthorized |
| 权限不足 | 403 | Forbidden |
| 资源不存在或跨 tenant 访问 | 404 | Not Found（不泄露资源存在性） |
| 请求参数错误 | 400 | Bad Request |
| 角色名冲突 | 409 | Conflict |

## 3. 非功能需求

### 3.1 模块间一致性
- 权限码字符串在各模块间必须一致: `doc.read`, `doc.write`, `doc.delete`, `doc.write.any`, `role.manage`
- JWT payload 结构统一: `{user_id, tenant_id, exp}`
- 模型字段名与 README.md 一致

### 3.2 安全性
- 密码不得明文存储
- JWT 必须验证签名和过期时间
- 所有接口必须进行权限检查
- 登录失败统一返回 401，不区分"用户名不存在"和"密码错误"，防止用户名枚举攻击

### 3.3 租户隔离
- 文档操作仅限本 tenant
- 角色分配需验证 user 和 role 同 tenant
- 跨 tenant 资源访问返回 404（不泄露存在性）

## 4. 约束条件

- `app.py` 不可修改
- `models.py` 已完整实现，不需要修改
- `middleware.py` 已完整实现，不需要修改
- 仅需实现: `routes_auth.py`, `routes_document.py`, `routes_role.py`
- **Blueprint 导出接口约束**：
  - `routes_auth.py` 必须导出 `auth_bp = Blueprint('auth_bp', __name__)`
  - `routes_document.py` 必须导出 `document_bp = Blueprint('document_bp', __name__)`
  - `routes_role.py` 必须导出 `role_bp = Blueprint('role_bp', __name__)`
  - 变量名不可更改，否则 `app.py` 导入失败

## 5. 验收标准

### 5.1 接口可用性
1. 所有 API 接口可正常调用：POST /login, GET/POST/PUT/DELETE /documents, POST/GET /roles, PUT /roles/<id>/permissions, POST/DELETE /users/<id>/roles

### 5.2 测试用例通过（逐条映射 test_basic.py）
2. `test_missing_token_returns_401` — 无 token 访问受保护 API → 401
3. `test_invalid_jwt_returns_401` — 非法 JWT → 401
4. `test_expired_jwt_returns_401` — 过期 JWT → 401
5. `test_admin_can_create_role` — 拥有 role.manage 权限的用户可创建角色 → 201
6. `test_non_admin_cannot_create_role` — 无 role.manage 权限的用户创建角色 → 403
7. `test_role_inheritance_works` — 子角色继承父角色权限，用户通过子角色获得父角色权限
8. `test_inheritance_cycle_rejected` — 继承链环检测，设置循环父角色 → 400
9. `test_viewer_can_read` — 拥有 doc.read 权限的用户可读取文档列表 → 200
10. `test_viewer_cannot_post` — 仅 doc.read 权限的用户创建文档 → 403
11. `test_editor_can_edit_own` — 拥有 doc.write 权限的用户可编辑自己的文档 → 200
12. `test_editor_cannot_edit_others` — 拥有 doc.write 权限的用户编辑他人文档 → 403
13. `test_admin_has_write_any` — 拥有 doc.write.any 权限的用户可编辑任意文档 → 200
14. `test_no_read_permission_returns_403` — 无任何角色的用户访问文档 → 403
15. `test_cross_tenant_document_returns_404` — 跨 tenant 访问文档 → 404
16. `test_cross_tenant_role_forbidden` — 跨 tenant 分配角色 → 403 或 404
17. `test_list_documents_only_own_tenant` — 文档列表仅包含本 tenant 的文档
18. `test_add_permission_propagates` — 给父角色加权限后，子角色用户自动获得该权限
19. `test_remove_permission_revokes` — 从父角色移除权限后，子角色用户丧失该权限
20. `test_multi_role_union` — 用户拥有多个角色时，权限取并集

### 5.3 行为验证
21. 角色继承链正确传递权限（递归向上查找）
22. 继承链循环被正确检测并拒绝
23. 多租户隔离有效（跨 tenant 访问返回 404，不泄露存在性）
24. 权限并集正确（多角色用户拥有所有角色权限的并集）
25. PUT /roles/<id>/permissions 的 permissions 字段为全量替换语义
