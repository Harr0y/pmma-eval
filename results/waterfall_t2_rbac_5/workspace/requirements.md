# 需求分析文档 — T2-3 RBAC 权限管理系统

## 1. 项目概述

基于 Flask 的多租户 RBAC（基于角色的访问控制）权限管理系统，支持角色继承、权限代码、租户隔离。

## 2. 功能需求

### 2.1 数据模型

| 模型 | 字段 | 说明 |
|------|------|------|
| **Tenant** | id, name | 租户 |
| **User** | id, tenant_id (FK), username (unique), password_hash, created_at | 用户，归属租户 |
| **Role** | id, tenant_id (FK), name, parent_role_id (nullable self-ref FK) | 角色，支持父角色继承 |
| **Permission** | id, code | 权限代码，如 `doc.read`, `doc.write`, `doc.delete`, `doc.write.any`, `role.manage` |
| **role_permissions** | role_id, permission_id | 角色-权限多对多关联表 |
| **user_roles** | user_id, role_id | 用户-角色多对多关联表 |
| **Document** | id, tenant_id (FK), owner_id (FK), title, content | 文档，归属租户和用户 |

### 2.2 认证接口（routes_auth.py）

**POST /login**
- 请求体：`{"username": str, "password": str}`
- 成功响应：`{"status": "ok", "data": {"token": str}}`
- JWT payload：`{"user_id": int, "tenant_id": int, "exp": timestamp}`
- 密码验证：使用 `middleware.hash_password()` 对输入密码哈希后比对
- 错误：
  - 400：username 或 password 缺失
  - 401：用户名不存在或密码错误

### 2.3 文档接口（routes_document.py）

**GET /documents**
- 权限要求：`doc.read`
- 行为：返回当前用户所属租户的所有文档列表
- 响应：`{"status": "ok", "data": [{"id", "tenant_id", "owner_id", "title", "content"}, ...]}`

**GET /documents/<id>**
- 权限要求：`doc.read`
- 行为：获取单个文档，仅限同租户
- 错误：404（文档不存在或不同租户）

**POST /documents**
- 权限要求：`doc.write`
- 请求体：`{"title": str, "content": str}`
- 行为：创建文档，tenant_id 从 JWT 获取，owner_id 为当前用户
- 成功状态码：**201**
- 响应：`{"status": "ok", "data": {"id", "tenant_id", "owner_id", "title", "content"}}`

**PUT /documents/<id>**
- 权限要求：`doc.write` + （是文档 owner 或拥有 `doc.write.any` 权限）
- 请求体：`{"title": str, "content": str}`（部分更新）
- 行为：更新文档，仅限同租户
- 错误：
  - 404：文档不存在或不同租户
  - 403：不是 owner 且无 `doc.write.any` 权限

**DELETE /documents/<id>**
- 权限要求：`doc.delete`
- 行为：删除文档，仅限同租户
- 错误：
  - 404：文档不存在或不同租户
  - 403：无 `doc.delete` 权限

### 2.4 角色管理接口（routes_role.py）

**POST /roles**
- 权限要求：`role.manage`
- 请求体：`{"name": str, "permissions": [str, ...], "parent_role_id": int|null}`
- 行为：在当前租户下创建角色，关联权限
- 成功状态码：**201**
- 错误：
  - 400：name 缺失
  - 409：同租户内角色名重复

**GET /roles**
- 权限要求：`role.manage`
- 行为：列出当前租户的所有角色
- 响应：`{"status": "ok", "data": [{"id", "name", "parent_role_id", "permissions": [str, ...]}, ...]}`

**PUT /roles/<id>/permissions**
- 权限要求：`role.manage`
- 请求体：`{"permissions": [str, ...], "parent_role_id": int|null}`（**两个字段均为可选**，未传递的字段保持原值不变）
- 行为：部分更新 — 仅更新请求体中传递的字段
  - 传 `permissions`：替换角色的权限集
  - 传 `parent_role_id`：更新父角色（传 null 可清除父角色）
  - 两个字段都传：同时更新
- 错误：
  - 404：角色不存在
  - 400：设置 parent_role_id 导致继承链循环

**POST /users/<id>/roles**
- 权限要求：`role.manage`
- 请求体：`{"role_id": int}`
- 行为：给用户分配角色。**目标用户必须与当前操作者同租户，角色也必须属于当前租户**
- 错误：
  - 404：用户或角色不存在
  - 403：目标用户或角色不在同租户

**DELETE /users/<id>/roles/<role_id>**
- 权限要求：`role.manage`
- 行为：移除用户角色（幂等）
- 错误：404（用户不存在）

### 2.5 权限继承

- 角色通过 `parent_role_id` 形成继承链
- 用户权限 = 所有直接角色的权限 ∪ 沿继承链向上收集的权限
- `_collect_role_permissions()` 已在 middleware.py 中实现，递归遍历 parent_role_id 链
- 继承链中如存在环，`_collect_role_permissions()` 通过 visited 集合防止无限递归
- **创建/修改角色时必须主动检测循环**，不能依赖 middleware 的 visited 防护

### 2.6 多租户隔离

- 所有数据操作（文档、角色）严格限定在当前用户的 tenant_id 范围内
- 跨租户访问文档返回 404
- 跨租户分配角色返回 403 或 404

## 3. 非功能需求

### 3.1 安全性
- JWT 使用 HS256 算法签名
- 密码使用 SHA-256 哈希存储（demo 级别）
- 所有受保护接口必须验证 JWT token

### 3.2 错误处理
- 缺失/无效/过期 token → 401
- 权限不足 → 403
- 资源不存在 → 404
- 请求参数错误 → 400

### 3.3 接口返回格式
```json
{"status": "ok", "data": ...}
{"status": "error", "message": "错误描述"}
```

## 4. 验收标准

1. 所有上述 API 接口可正常调用，返回格式符合规范
2. `python -m pytest tests/test_basic.py -v` 全部通过（exit code 0），包括：
   - 认证测试（缺失 token、无效 JWT、过期 JWT）
   - 角色管理测试（创建角色、非管理员禁止、继承生效、循环拒绝）
   - 文档 RBAC 测试（viewer 可读、viewer 不可写、editor 编辑自己的、editor 不可编辑他人的、admin 有 write.any、无权限 403）
   - 多租户测试（跨租户文档 404、跨租户角色禁止、文档列表仅本租户）
   - 权限继承测试（添加权限传播、移除权限撤销、多角色权限取并集）

## 5. 约束与已知限制

- `app.py` 不可修改（已声明）
- `models.py` 已完成，不需修改
- `middleware.py` 已完成（JWT 验证、权限检查、继承遍历），不需修改
- 需要实现的文件：`routes_auth.py`、`routes_document.py`、`routes_role.py`
- 会话存储：内存（SQLite），非持久化
