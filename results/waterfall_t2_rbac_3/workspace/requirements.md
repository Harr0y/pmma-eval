# 需求分析文档 — T2-3 RBAC 权限管理系统

## 1. 项目概述

实现一个基于 Flask 的多租户 RBAC（基于角色的访问控制）权限管理系统，支持角色继承、权限检查、文档 CRUD 操作。系统采用多模块架构，代码分布在 6 个文件中。

## 2. 模块划分与现有代码状态

| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 应用工厂 | `app.py` | ✅ 已完成 | Flask app 工厂 + DB 初始化（不可修改） |
| 数据模型 | `models.py` | ✅ 已完成 | Tenant, User, Role, Permission, Document + 关联表 |
| 认证中间件 | `middleware.py` | ✅ 已完成 | JWT 验证 + 权限检查（含继承遍历） |
| 认证接口 | `routes_auth.py` | ❌ 待实现 | 登录接口 |
| 文档接口 | `routes_document.py` | ❌ 待实现 | 文档 CRUD + RBAC |
| 角色管理接口 | `routes_role.py` | ❌ 待实现 | 角色管理 + 用户角色分配 |

## 3. 功能需求

### 3.1 认证接口 (routes_auth.py)

**FR-AUTH-001**: POST /login
- **请求**: `{"username": str, "password": str}`
- **成功响应**: `{"status": "ok", "data": {"token": str}}`，HTTP 200
- **JWT payload**: `{"user_id": int, "tenant_id": int, "exp": timestamp}`
- **密码验证**: 使用 `middleware.hash_password()` 进行 SHA256 哈希比对
- **错误处理**:
  - 缺少 username 或 password → 400
  - 用户不存在或密码错误 → 401

### 3.2 文档接口 (routes_document.py)

**FR-DOC-001**: GET /documents — 列出文档
- **权限要求**: `doc.read`
- **范围**: 仅返回当前用户所属 tenant 的文档
- **响应**: `{"status": "ok", "data": [{"id", "tenant_id", "owner_id", "title", "content"}, ...]}`

**FR-DOC-002**: GET /documents/<id> — 获取单个文档
- **权限要求**: `doc.read`
- **范围**: 同 tenant（不同 tenant 返回 404）
- **错误**: 文档不存在或不同 tenant → 404

**FR-DOC-003**: POST /documents — 创建文档
- **权限要求**: `doc.write`
- **请求**: `{"title": str, "content": str}`
- **自动填充**: tenant_id 从 JWT 获取，owner_id 为当前用户
- **响应**: `{"status": "ok", "data": {"id", "tenant_id", "owner_id", "title", "content"}}`，HTTP 201

**FR-DOC-004**: PUT /documents/<id> — 更新文档
- **权限要求**: `doc.write` + (owner 或 `doc.write.any` 权限) + 同 tenant
- **请求**: `{"title": str, "content": str}`（至少提供一个）
- **错误**:
  - 文档不存在或不同 tenant → 404
  - 非 owner 且无 `doc.write.any` → 403

**FR-DOC-005**: DELETE /documents/<id> — 删除文档
- **权限要求**: `doc.delete` + 同 tenant
- **成功响应**: `{"status": "ok", "data": null}`
- **错误**: 文档不存在或不同 tenant → 404

### 3.3 角色管理接口 (routes_role.py)

**FR-ROLE-001**: POST /roles — 创建角色
- **权限要求**: `role.manage`
- **请求**: `{"name": str, "permissions": [str, ...], "parent_role_id": int|null}`
- **字段说明**:
  - `name`（必填）：角色名称
  - `permissions`（必填）：权限码列表，可为空列表 `[]`
  - `parent_role_id`（可选）：父角色 ID，可省略（等同于 null）
- **约束**:
  - name 不能为空
  - 同 tenant 内角色名不能重复（否则 409）
  - parent_role_id 必须属于同 tenant（若提供且非 null）
  - permissions 中的 code 必须在 Permission 表中存在；空列表 `[]` 合法（表示无直接权限）
- **响应**: `{"status": "ok", "data": {"id", "name", "parent_role_id", "permissions"}}`，HTTP 201

**FR-ROLE-002**: GET /roles — 列出角色
- **权限要求**: `role.manage`
- **范围**: 仅返回当前 tenant 的角色
- **响应**: `{"status": "ok", "data": [{"id": int, "name": str, "parent_role_id": int|null, "permissions": [str, ...]}, ...]}`
  - 每个角色对象至少包含 `id` 和 `name` 字段
  - `permissions` 字段应包含该角色直接关联的权限码列表

**FR-ROLE-003**: PUT /roles/<id>/permissions — 更新角色权限和/或父角色
- **权限要求**: `role.manage`
- **请求**: `{"permissions": [str, ...], "parent_role_id": int|null}`
- **字段说明**（两个字段均为可选，可单独或同时提供）：
  - `permissions`（可选）：替换角色的权限集。若省略，不修改权限
  - `parent_role_id`（可选）：设置父角色。若省略，不修改父角色；若提供 null，清除父角色
- **关键约束**: 必须检测继承链循环（A→B→A）
- **错误**:
  - 角色不存在 → 404
  - 设置 parent_role_id 后形成循环 → 400
  - parent_role_id 不属于同 tenant → 400

**FR-ROLE-004**: POST /users/<id>/roles — 分配角色
- **权限要求**: `role.manage`
- **请求**: `{"role_id": int}`
- **约束**: 用户和角色必须属于同 tenant
- **幂等性**: 如果角色已分配，不报错
- **错误**:
  - 用户不存在 → 404
  - 角色不存在 → 404
  - 用户和角色不属于同 tenant → 403

**FR-ROLE-005**: DELETE /users/<id>/roles/<role_id> — 移除角色
- **权限要求**: `role.manage`
- **幂等性**: 如果角色未分配给该用户，不报错（返回成功）
- **错误**:
  - 用户不存在 → 404
  - role_id 对应的角色不存在 → 不报错（幂等处理）

## 4. 数据模型需求

### 4.1 已定义模型（不可修改）

| 模型 | 关键字段 |
|------|---------|
| Tenant | id, name |
| User | id, tenant_id(FK), username(unique), password_hash, created_at |
| Role | id, tenant_id(FK), name, parent_role_id(nullable self-ref FK) |
| Permission | id, code(unique) |
| role_permissions | role_id, permission_id (M2M) |
| user_roles | user_id, role_id (M2M) |
| Document | id, tenant_id(FK), owner_id(FK→User), title, content |

### 4.2 权限码定义

| 权限码 | 用途 |
|--------|------|
| `doc.read` | 读取文档 |
| `doc.write` | 创建文档、编辑自己拥有的文档 |
| `doc.write.any` | 编辑任何人的文档（需配合 doc.write） |
| `doc.delete` | 删除文档 |
| `role.manage` | 管理角色和分配 |

### 4.3 角色继承机制

- 角色通过 `parent_role_id` 形成树形继承链
- 权限沿继承链向上累加（子角色拥有父角色的所有权限）
- 用户拥有多个角色时，权限取所有角色权限的**并集**（含各自继承链）
- `middleware._collect_role_permissions()` 已实现递归收集
- 禁止循环继承

## 5. 接口一致性要求

- 所有成功响应格式：`{"status": "ok", "data": ...}`
- 所有错误响应格式：`{"status": "error", "message": "错误描述"}`
- JWT payload 结构：`{"user_id": int, "tenant_id": int, "exp": timestamp}`
- Blueprint 名称必须与 app.py 中注册的一致：`auth_bp`, `document_bp`, `role_bp`

## 6. 验收标准

### AC-1: 所有 API 接口可正常调用
- [ ] POST /login 返回有效 JWT
- [ ] GET /documents 返回文档列表（有 doc.read 权限）
- [ ] GET /documents/<id> 返回单个文档
- [ ] POST /documents 创建文档（HTTP 201）
- [ ] PUT /documents/<id> 更新文档
- [ ] DELETE /documents/<id> 删除文档
- [ ] POST /roles 创建角色（HTTP 201）
- [ ] GET /roles 列出角色
- [ ] PUT /roles/<id>/permissions 更新权限
- [ ] POST /users/<id>/roles 分配角色
- [ ] DELETE /users/<id>/roles/<role_id> 移除角色

### AC-2: tests/test_basic.py 全部测试通过
- [ ] TestAuth: 3 个测试通过
- [ ] TestRoleManagement: 4 个测试通过
- [ ] TestDocumentRBAC: 6 个测试通过
- [ ] TestMultiTenant: 3 个测试通过
- [ ] TestPermissionInheritance: 3 个测试通过

### AC-3: 安全性
- [ ] 无 token → 401
- [ ] 无效 JWT → 401
- [ ] 过期 JWT → 401
- [ ] 权限不足 → 403
- [ ] 跨 tenant 操作被隔离

### AC-4: 边界条件
- [ ] 继承链循环检测
- [ ] 角色名重复检测（同 tenant）
- [ ] 幂等的角色分配/移除
- [ ] 空 permissions 列表处理（合法，表示无直接权限）
- [ ] PUT /roles/<id>/permissions 字段可选性（permissions 和 parent_role_id 均可省略）
- [ ] 跨租户角色分配返回 403
- [ ] 多角色权限取并集
