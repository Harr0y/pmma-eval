# 需求分析文档 — T2-3 RBAC 权限管理系统

## 1. 项目概述

实现一个基于角色的访问控制（RBAC）系统，支持多租户、角色继承和细粒度权限管理。系统采用 Flask 框架，代码分布在多个模块中。

## 2. 功能需求

### FR-1: 数据模型

| 模型 | 字段 | 约束 |
|------|------|------|
| Tenant | id (PK), name | name NOT NULL |
| User | id (PK), tenant_id (FK→Tenant), username, password_hash, created_at | username UNIQUE, tenant_id NOT NULL |
| Role | id (PK), tenant_id (FK→Tenant), name, parent_role_id (FK→Role, self-ref) | tenant_id NOT NULL, parent_role_id nullable |
| Permission | id (PK), code | code UNIQUE NOT NULL |
| role_permissions | role_id (FK→Role), permission_id (FK→Permission) | 复合主键 |
| user_roles | user_id (FK→User), role_id (FK→Role) | 复合主键 |
| Document | id (PK), tenant_id (FK→Tenant), owner_id (FK→User), title, content | tenant_id/owner_id NOT NULL |

**已实现状态**：`models.py` 已完整实现，无需修改。

### FR-2: 认证中间件

- **JWT 验证**：从 `Authorization: Bearer <token>` 头提取并验证 token
- **缺失 token** → 401 `{"status": "error", "message": "Missing token"}`
- **无效/过期 token** → 401 `{"status": "error", "message": "Invalid or expired token"}`
- **权限检查**：沿 `parent_role_id` 继承链向上递归收集权限
- **装饰器**：`check_permission(code)` — 验证特定权限；`require_auth` — 仅验证登录
- **循环检测**：继承链遍历时使用 `visited` 集合防止死循环

**已实现状态**：`middleware.py` 已完整实现，无需修改。

### FR-3: 认证接口 (routes_auth.py)

| 端点 | 方法 | 权限 | 描述 |
|------|------|------|------|
| `/login` | POST | 无 | 用户登录，返回 JWT |

**请求**：`{"username": str, "password": str}`
**成功响应**：`{"status": "ok", "data": {"token": str}}`
**JWT payload**：`{user_id, tenant_id, exp}`

**错误处理**：
- 缺少 username 或 password → 400
- 用户不存在或密码错误 → 401

**实现状态**：需实现（当前为空 Blueprint）

### FR-4: 文档接口 (routes_document.py)

| 端点 | 方法 | 权限要求 | 描述 |
|------|------|----------|------|
| `/documents` | GET | `doc.read` | 列出当前租户的文档 |
| `/documents/<id>` | GET | `doc.read` + 同租户 | 获取单个文档 |
| `/documents` | POST | `doc.write` | 创建文档 |
| `/documents/<id>` | PUT | `doc.write` + (owner 或 `doc.write.any`) | 更新文档 |
| `/documents/<id>` | DELETE | `doc.delete` + 同租户 | 删除文档 |

**多租户隔离**：
- GET /documents 只返回当前用户租户的文档
- GET/PUT/DELETE 对不同租户的文档返回 404（先检查同租户，再检查权限）

**PUT 权限逻辑**：
- owner 可以编辑自己的文档
- 拥有 `doc.write.any` 权限的用户可以编辑任何文档
- 两者都不满足 → 403

**实现状态**：需实现（当前为空 Blueprint）

### FR-5: 角色管理接口 (routes_role.py)

| 端点 | 方法 | 权限要求 | 描述 |
|------|------|----------|------|
| `/roles` | POST | `role.manage` | 创建角色 |
| `/roles` | GET | `role.manage` | 列出当前租户的角色（需管理员权限，与 POST/PUT/DELETE 一致） |
| `/roles/<id>/permissions` | PUT | `role.manage` | 替换权限集 + 更新 parent |
| `/users/<id>/roles` | POST | `role.manage` | 分配角色给用户 |
| `/users/<id>/roles/<role_id>` | DELETE | `role.manage` | 移除用户角色 |

**POST /roles**：
- 请求：`{"name": str, "parent_role_id": int|null, "permissions": [str, ...]}`
- 成功响应：201 `{"status": "ok", "data": {"id", "name", "parent_role_id", "permissions"}}`
- 验证：name 不能为空、同名角色不能在同一租户重复、parent_role_id 必须属于同租户
- **无效权限码处理**：如果 permissions 数组中包含不存在的权限码，返回 400 错误
- 错误：400（参数缺失/parent 无效/无效权限码）、409（角色名重复）

**PUT /roles/<id>/permissions**：
- 请求：`{"permissions": [str, ...], "parent_role_id": int|null}`
- **部分更新语义**：`permissions` 和 `parent_role_id` 均为可选字段，不传则保持原值
- **继承链循环检测**：设置 parent_role_id 时，必须检查是否形成环
- 错误：404（角色不存在）、400（循环检测或 parent 无效）

**POST /users/<id>/roles**：
- 请求：`{"role_id": int}`
- 用户和角色必须属于同一租户
- 错误：404（用户或角色不存在）、403（用户和角色不属于同一租户）

**DELETE /users/<id>/roles/<role_id>**：
- 幂等操作：角色未分配时也不报错
- 跨租户保护：目标用户属于不同租户时返回 404
- 错误：404（用户不存在或跨租户）

**实现状态**：需实现（当前为空 Blueprint）

## 3. 接口返回格式

统一格式：
- 成功：`{"status": "ok", "data": ...}`
- 错误：`{"status": "error", "message": "错误描述"}`

## 4. 验收标准

| 编号 | 验收标准 | 验证方式 |
|------|----------|----------|
| AC-1 | POST /login 可正常登录并返回有效 JWT | test_basic.py::TestAuth |
| AC-2 | 缺失/无效/过期 token 返回 401 | test_basic.py::TestAuth |
| AC-3 | 角色创建、列表、权限更新、用户分配/移除正常 | test_basic.py::TestRoleManagement |
| AC-4 | 角色继承链正确传递权限 | test_basic.py::TestPermissionInheritance |
| AC-5 | 继承链循环检测生效 | test_basic.py::TestRoleManagement::test_inheritance_cycle_rejected |
| AC-6 | 文档 CRUD 操作权限检查正确 | test_basic.py::TestDocumentRBAC |
| AC-7 | 多租户隔离：不同租户无法访问对方文档 | test_basic.py::TestMultiTenant |
| AC-8 | 多租户隔离：跨租户角色分配被拒绝 | test_basic.py::TestMultiTenant::test_cross_tenant_role_forbidden |
| AC-9 | 用户多角色权限取并集 | test_basic.py::TestPermissionInheritance::test_multi_role_union |
| AC-10 | 所有接口返回格式符合统一规范 `{"status": "ok/error", "data/message"}` | 所有接口的响应结构 |
| AC-11 | 所有 tests/test_basic.py 测试用例通过 | pytest -v |

## 5. 模块间接口一致性要求

| 接口 | 涉及模块 | 说明 |
|------|----------|------|
| 权限码字符串 | middleware ↔ routes | `doc.read`, `doc.write`, `doc.delete`, `doc.write.any`, `role.manage` |
| JWT payload | routes_auth ↔ middleware | `{user_id, tenant_id, exp}` |
| 模型字段名 | routes ↔ models | 与 models.py 中定义完全一致 |
| Blueprint 名称 | routes ↔ app | `auth_bp`, `document_bp`, `role_bp` |

## 6. 非功能性需求

- 密码哈希：使用 `middleware.hash_password()`（SHA-256，demo 用途）
- JWT 算法：HS256
- 数据库：SQLite（开发环境）
- app.py 不允许修改
