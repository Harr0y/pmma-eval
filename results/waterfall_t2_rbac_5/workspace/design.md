# 方案设计文档 — T2-3 RBAC 权限管理系统

## 1. 数据库表设计

数据库使用 SQLite，通过 Flask-SQLAlchemy ORM 定义。表结构已在 `models.py` 中定义完成，无需修改。

### 1.1 表关系图

```
Tenant ──1:N──> User ──M:N──> Role ──M:N──> Permission
   │              │           │
   │              │           └── self-ref (parent_role_id)
   │              │
   └──1:N──> Document <──N:1── User (owner)
```

### 1.2 关联表

| 关联表 | 字段 | 说明 |
|--------|------|------|
| `role_permissions` | role_id (FK→role.id), permission_id (FK→permission.id) | 角色拥有的权限 |
| `user_roles` | user_id (FK→user.id), role_id (FK→role.id) | 用户拥有的角色 |

## 2. API 端点设计

### 2.1 认证接口（ATU-003：routes_auth.py）

| 方法 | 路径 | 权限 | 请求体 | 成功响应 | 错误 |
|------|------|------|--------|----------|------|
| POST | /login | 无 | `{"username": str, "password": str}` | `{"status":"ok","data":{"token":str}}` (200) | 400(参数缺失), 401(凭据错误) |

**实现逻辑**：
1. 从请求体获取 username 和 password
2. 缺失任一字段 → 返回 400
3. 查询 User.where(username=username)
4. 用户不存在或 hash_password(password) != user.password_hash → 返回 401
5. 生成 JWT：payload = {user_id, tenant_id, exp=now+24h}
6. 返回 {"status": "ok", "data": {"token": token}}

**关键依赖**：
- `middleware.hash_password()` — 密码哈希
- `models.User` — 用户查询
- `jwt.encode()` — JWT 生成
- `current_app.config['JWT_SECRET']` — 签名密钥
- `current_app.config['JWT_EXPIRY_HOURS']` — 过期时间

### 2.2 文档接口（ATU-004：routes_document.py）

| 方法 | 路径 | 权限 | 请求体 | 成功响应 | 错误 |
|------|------|------|--------|----------|------|
| GET | /documents | doc.read | - | `{"status":"ok","data":[...]}` (200) | 401, 403 |
| GET | /documents/\<id\> | doc.read | - | `{"status":"ok","data":{...}}` (200) | 401, 403, 404 |
| POST | /documents | doc.write | `{"title":str,"content":str}` | `{"status":"ok","data":{...}}` (201) | 401, 403 |
| PUT | /documents/\<id\> | doc.write + owner/write.any | `{"title":str,"content":str}` | `{"status":"ok","data":{...}}` (200) | 401, 403, 404 |
| DELETE | /documents/\<id\> | doc.delete | - | `{"status":"ok","data":null}` (200) | 401, 403, 404 |

**实现逻辑**：

**GET /documents**：
1. `@check_permission('doc.read')` 装饰器验证认证 + 权限
2. 查询 `Document.query.filter_by(tenant_id=g.current_user.tenant_id).all()`
3. 返回文档列表（序列化为 dict 数组）

**GET /documents/\<id\>**：
1. `@check_permission('doc.read')` 验证
2. 查询文档，检查 tenant_id == g.current_user.tenant_id
3. 不匹配 → 404
4. 返回文档详情

**POST /documents**：
1. `@check_permission('doc.write')` 验证
2. 创建 Document(tenant_id=g.current_user.tenant_id, owner_id=g.current_user.id, title=..., content=...)
3. db.session.add + commit
4. 返回 201 + 文档数据

**PUT /documents/\<id\>**：
1. `@check_permission('doc.write')` 验证，获取 g.current_permissions
2. 查询文档，检查 tenant_id
3. 不是 owner 且 'doc.write.any' not in g.current_permissions → 403
4. 更新 title/content（仅更新请求体中提供的字段）
5. commit + 返回 200

**DELETE /documents/\<id\>**：
1. `@check_permission('doc.delete')` 验证
2. 查询文档，检查 tenant_id
3. 不匹配 → 404
4. db.session.delete + commit
5. 返回 200

**文档序列化格式**：
```python
{"id": doc.id, "tenant_id": doc.tenant_id, "owner_id": doc.owner_id, "title": doc.title, "content": doc.content}
```

### 2.3 角色管理接口（ATU-005：routes_role.py）

| 方法 | 路径 | 权限 | 请求体 | 成功响应 | 错误 |
|------|------|------|--------|----------|------|
| POST | /roles | role.manage | `{"name":str,"permissions":[str],"parent_role_id":int\|null}` | `{"status":"ok","data":{...}}` (201) | 401, 403, 400, 409 |
| GET | /roles | role.manage | - | `{"status":"ok","data":[...]}` (200) | 401, 403 |
| PUT | /roles/\<id\>/permissions | role.manage | `{"permissions":[str],"parent_role_id":int\|null}` (均可选) | `{"status":"ok","data":{...}}` (200) | 401, 403, 404, 400 |
| POST | /users/\<id\>/roles | role.manage | `{"role_id":int}` | `{"status":"ok","data":null}` (200) | 401, 403, 404 |
| DELETE | /users/\<id\>/roles/\<role_id\> | role.manage | - | `{"status":"ok","data":null}` (200) | 401, 403, 404 |

**实现逻辑**：

**POST /roles**：
1. `@check_permission('role.manage')` 验证
2. 获取 name（必填）、permissions（可选，默认 []）、parent_role_id（可选，默认 null）
3. name 缺失 → 400
4. 检查同租户内角色名是否重复 → 409
5. 如果提供 parent_role_id：验证父角色存在且属于同租户
6. 创建 Role + 关联 Permission（通过 code 查询）
7. 返回 201 + 角色详情

**GET /roles**：
1. `@check_permission('role.manage')` 验证
2. 查询 `Role.query.filter_by(tenant_id=g.current_user.tenant_id).all()`
3. 每个角色序列化：id, name, parent_role_id, permissions（code 字符串数组）

**PUT /roles/\<id\>/permissions**：
1. `@check_permission('role.manage')` 验证
2. 查询角色 → 404
3. 如果请求体包含 `parent_role_id`：
   - 如果非 null：验证父角色存在且属于同租户
   - **循环检测**：检查设置 parent_role_id 后是否形成环（见算法 3.1）
   - 通过后更新 role.parent_role_id
4. 如果请求体包含 `permissions`：
   - 清除角色现有权限：`role.permissions = []`
   - 通过 code 查询 Permission 并关联：`role.permissions.extend(Permission.query.filter(Permission.code.in_(codes)).all())`
5. commit + 返回 200

**POST /users/\<id\>/roles**：
1. `@check_permission('role.manage')` 验证
2. 查询目标用户 → 404
3. 查询目标角色 → 404
4. **租户校验**：目标用户 tenant_id != 操作者 tenant_id → 403；角色 tenant_id != 操作者 tenant_id → 403
5. 添加关联：`user.roles.append(role)`
6. commit + 返回 200

**DELETE /users/\<id\>/roles/\<role_id\>**：
1. `@check_permission('role.manage')` 验证
2. 查询目标用户 → 404
3. 从 user.roles 中移除指定角色（如果存在）
4. 幂等操作：角色不在用户角色列表中也不报错
5. commit + 返回 200

**角色序列化格式**：
```python
{"id": role.id, "name": role.name, "parent_role_id": role.parent_role_id, "permissions": [p.code for p in role.permissions]}
```

## 3. 关键算法

### 3.1 继承链循环检测算法

当设置 `parent_role_id` 时，需要检测是否会形成环。

```
输入：role_id（要修改的角色），new_parent_id（新父角色，可能为 null）
输出：True（存在环） / False（无环）

1. 如果 new_parent_id 为 null → 无环，返回 False
2. visited = set()
3. current = new_parent_id
4. 循环：
   a. 如果 current == role_id → 发现环，返回 True
   b. 如果 current in visited → 已遍历过的链（middleware 已有的环），返回 False
   c. visited.add(current)
   d. 查询 Role(current).parent_role_id
   e. 如果 parent_role_id 为 null → 到达链顶端，返回 False
   f. current = parent_role_id
5. 返回 False
```

**关键点**：
- 循环检测仅在**创建角色**（设置 parent_role_id）和**修改角色权限**（更新 parent_role_id）时执行
- middleware 中的 `_collect_role_permissions()` 已有 visited 防护防止运行时无限递归
- 但循环检测应在写入时就拒绝，不应依赖 middleware 的运行时防护

### 3.2 权限继承遍历

已在 `middleware._collect_role_permissions()` 中实现：
- 从给定角色开始，收集其直接权限
- 递归遍历 parent_role_id 链，收集父角色权限
- 使用 visited 集合防止环导致的无限递归
- `get_user_permissions()` 对用户所有角色调用 `_collect_role_permissions()` 并取并集

## 4. JWT 设计

### 4.1 Payload 结构

```json
{
  "user_id": 1,
  "tenant_id": 1,
  "exp": 1717200000
}
```

### 4.2 生成参数

- 算法：HS256
- 密钥：`current_app.config['JWT_SECRET']`（默认 'dev-secret-key'）
- 过期时间：`current_app.config['JWT_EXPIRY_HOURS']`（默认 24 小时）

### 4.3 中间件验证流程

`middleware.get_current_user()` 已实现：
1. 从 `Authorization: Bearer <token>` 提取 token
2. 缺失 → 401
3. `decode_token()` 解码验证 → 失败返回 None → 401
4. 查询 User → 不存在 → 401
5. 返回 (user, None)

`middleware.check_permission(code)` 装饰器已实现：
1. 调用 `get_current_user()`
2. 调用 `get_user_permissions(user)` 获取权限集
3. 检查 code 是否在权限集中
4. 不在 → 403
5. 设置 `g.current_user` 和 `g.current_permissions`

## 5. 模块依赖关系

```
app.py (不可修改)
  ├── models.py (不可修改)
  │     └── 定义所有数据模型
  ├── middleware.py (不可修改)
  │     ├── 导入：models (User, Role, Permission, role_permissions, user_roles)
  │     ├── 导入：app (db)
  │     └── 提供：hash_password, decode_token, get_current_user, get_user_permissions, check_permission, require_auth
  ├── routes_auth.py (ATU-003)
  │     ├── 导入：models (User)
  │     ├── 导入：middleware (hash_password)
  │     └── 导入：jwt, current_app
  ├── routes_document.py (ATU-004)
  │     ├── 导入：models (Document)
  │     ├── 导入：middleware (check_permission)
  │     └── 导入：app (db), flask (g)
  └── routes_role.py (ATU-005)
        ├── 导入：models (Role, Permission, User, role_permissions, user_roles)
        ├── 导入：middleware (check_permission)
        └── 导入：app (db), flask (g)
```

## 6. 实现计划

按 ATU 顺序执行：

| ATU | 文件 | 预估行数 | 依赖 |
|-----|------|----------|------|
| ATU-003 | routes_auth.py | ~25行 | 无（仅依赖 middleware + models） |
| ATU-004 | routes_document.py | ~70行 | ATU-003（确认认证链路正常） |
| ATU-005 | routes_role.py | ~120行 | ATU-004（确认权限检查链路正常） |

## 7. 错误处理统一规范

所有接口的异常处理遵循以下模式：

```python
from flask import jsonify

def error_response(message, status_code):
    return jsonify({"status": "error", "message": message}), status_code

def ok_response(data=None):
    return jsonify({"status": "ok", "data": data})
```

## 8. 测试覆盖对照

| 测试用例 | 对应接口 | 验证点 |
|----------|----------|--------|
| test_missing_token_returns_401 | 所有受保护接口 | middleware 401 处理 |
| test_invalid_jwt_returns_401 | 所有受保护接口 | middleware JWT 验证 |
| test_expired_jwt_returns_401 | 所有受保护接口 | middleware 过期处理 |
| test_admin_can_create_role | POST /roles | 创建角色 201 |
| test_non_admin_cannot_create_role | POST /roles | 403 权限拒绝 |
| test_role_inheritance_works | POST /roles + POST /users + GET /documents | 继承链权限收集 |
| test_inheritance_cycle_rejected | PUT /roles/\<id\>/permissions | 循环检测 400 |
| test_viewer_can_read | GET /documents | doc.read 权限 |
| test_viewer_cannot_post | POST /documents | 403 无 doc.write |
| test_editor_can_edit_own | PUT /documents/\<id\> | owner 可编辑 |
| test_editor_cannot_edit_others | PUT /documents/\<id\> | 403 非 owner 无 write.any |
| test_admin_has_write_any | PUT /documents/\<id\> | doc.write.any 全局编辑 |
| test_no_read_permission_returns_403 | GET /documents | 403 无 doc.read |
| test_cross_tenant_document_returns_404 | GET /documents/\<id\> | 租户隔离 |
| test_cross_tenant_role_forbidden | POST /users/\<id\>/roles | 跨租户 403/404 |
| test_list_documents_only_own_tenant | GET /documents | 列表租户隔离 |
| test_add_permission_propagates | PUT /roles/\<id\>/permissions + GET /documents | 父角色权限传播 |
| test_remove_permission_revokes | PUT /roles/\<id\>/permissions + GET /documents | 父角色权限撤销 |
| test_multi_role_union | POST /users/\<id\>/roles | 多角色权限并集 |
