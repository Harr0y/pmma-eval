# 方案设计文档 — T2-3 RBAC 权限管理系统

## 1. 架构总览

```
app.py (不变)
  ├── routes_auth.py    — 认证（POST /login）
  ├── routes_document.py — 文档 CRUD + RBAC
  ├── routes_role.py    — 角色管理 + 用户角色分配
  ├── middleware.py      — JWT 验证 + 权限检查（已实现）
  └── models.py         — 数据模型（已实现）
```

**不需要修改的文件**：`app.py`, `models.py`, `middleware.py`
**需要实现的文件**：`routes_auth.py`, `routes_document.py`, `routes_role.py`

## 2. API 端点设计

### 2.1 认证接口 — routes_auth.py

#### POST /login

```
请求: {"username": str, "password": str}
成功: 200 {"status": "ok", "data": {"token": str}}
错误: 400 {"status": "error", "message": "..."}  — username/password 缺失
错误: 401 {"status": "error", "message": "..."}  — 凭证无效
```

**实现逻辑**：
0. 使用 `request.get_json(silent=True)` 获取请求体，如果返回 None → 400 `{"status": "error", "message": "Invalid request"}`
1. 验证请求 JSON 包含 `username` 和 `password`，否则 400
2. 通过 `username` 查询 User，不存在则 401
3. 使用 `middleware.hash_password(password)` 哈希后与 `user.password_hash` 比较，不匹配则 401
4. 使用 `pyjwt.encode()` 生成 JWT，payload = `{user_id, tenant_id, exp}`，exp = 当前时间 + JWT_EXPIRY_HOURS
5. 返回 token

**关键导入**：
```python
from models import User
from middleware import hash_password
import jwt as pyjwt
from flask import current_app
import datetime
```

### 2.2 文档接口 — routes_document.py

#### GET /documents
```
权限: doc.read
成功: 200 {"status": "ok", "data": [{id, tenant_id, owner_id, title, content}, ...]}
错误: 401/403
```
**逻辑**：使用 `@check_permission('doc.read')` 装饰器，查询 `Document.query.filter_by(tenant_id=user.tenant_id).all()`

#### GET /documents/<id>
```
权限: doc.read + 同租户
成功: 200 {"status": "ok", "data": {id, tenant_id, owner_id, title, content}}
错误: 401/403/404
```
**逻辑**：
1. 使用 `@check_permission('doc.read')` 装饰器
2. 查询文档，不存在或 tenant_id != user.tenant_id → 404

#### POST /documents
```
权限: doc.write
成功: 201 {"status": "ok", "data": {id, tenant_id, owner_id, title, content}}
错误: 401/403/400
```
**逻辑**：
1. 使用 `@check_permission('doc.write')` 装饰器
2. 验证 title 不为空
3. 创建 Document(tenant_id=user.tenant_id, owner_id=user.id, title=title, content=content 或 request.get_json().get('content', ''))

#### PUT /documents/<id>
```
权限: doc.write + (owner 或 doc.write.any) + 同租户
成功: 200 {"status": "ok", "data": {id, tenant_id, owner_id, title, content}}
错误: 401/403/404
```
**逻辑**：
1. 使用 `@check_permission('doc.write')` 装饰器
2. 查询文档，不存在或 tenant_id != user.tenant_id → 404
3. 检查 owner：doc.owner_id == user.id 或 `doc.write.any` in g.current_permissions
4. 不满足 → 403
5. 更新 title 和 content（仅更新传入的字段）

#### DELETE /documents/<id>
```
权限: doc.delete + 同租户
成功: 200 {"status": "ok", "data": null}
错误: 401/403/404
```
**逻辑**：
1. 使用 `@check_permission('doc.delete')` 装饰器
2. 查询文档，不存在或 tenant_id != user.tenant_id → 404
3. 删除文档

**关键导入**：
```python
from models import Document
from middleware import check_permission
from flask import g
from app import db
```

### 2.3 角色管理接口 — routes_role.py

#### POST /roles
```
权限: role.manage
成功: 201 {"status": "ok", "data": {id, name, parent_role_id, permissions: [str, ...]}}
错误: 400/403/409
```
**逻辑**：
1. 使用 `@check_permission('role.manage')` 装饰器（无 role.manage 权限时装饰器自动返回 403）
2. 验证 name 非空
3. 检查同名角色在同一租户是否已存在 → 409
4. 如果提供了 parent_role_id，验证其存在且 `parent.tenant_id == g.current_user.tenant_id`（同租户），否则 → 400
5. 如果提供了 permissions，验证所有权限码存在于 Permission 表，无效权限码 → 400
6. 创建 Role，关联 permissions
7. 返回角色信息含权限码列表

#### GET /roles
```
权限: role.manage
成功: 200 {"status": "ok", "data": [{id, name, parent_role_id, permissions: [str, ...]}, ...]}
错误: 401/403
```
**逻辑**：查询当前租户所有角色，序列化含权限码

#### PUT /roles/<id>/permissions
```
权限: role.manage
成功: 200 {"status": "ok", "data": {id, name, parent_role_id, permissions: [str, ...]}}
错误: 400/403/404
```
**逻辑**：
1. 使用 `@check_permission('role.manage')` 装饰器
2. 查询角色，不存在 → 404
3. **部分更新**：只更新请求中包含的字段。如果请求体为空 `{}`，两个都不更新，直接返回 200
4. 如果传了 `permissions`：清空旧权限，关联新权限（验证权限码存在）
5. 如果传了 `parent_role_id`：
   - 验证 parent 存在且属于同租户
   - **循环检测**：从 parent_role_id 开始向上遍历继承链，如果遇到当前角色 id → 400
6. db.session.commit()

#### POST /users/<id>/roles
```
权限: role.manage
成功: 200 {"status": "ok", "data": null}
错误: 403/404
```
**逻辑**：
1. 使用 `@check_permission('role.manage')` 装饰器（无 role.manage 权限时装饰器自动返回 403）
2. 查询目标用户 `User.query.get(user_id)`，不存在 → 404
3. 查询角色 `Role.query.get(role_id)`，不存在 → 404
4. **跨租户检查**：验证 `target_user.tenant_id == role.tenant_id`（用户和角色必须属于同一租户），否则 → 403
5. 添加 user_roles 关联

#### DELETE /users/<id>/roles/<role_id>
```
权限: role.manage
成功: 200 {"status": "ok", "data": null}
错误: 401/403/404
```
**逻辑**：
1. 使用 `@check_permission('role.manage')` 装饰器（无 role.manage 权限时装饰器自动返回 403）
2. 查询目标用户 `User.query.get(user_id)`，不存在 → 404
3. **跨租户保护**：如果 `target_user.tenant_id != g.current_user.tenant_id` → 404
3. 删除 user_roles 关联（幂等，不存在也不报错）

**关键导入**：
```python
from models import Role, Permission, User, user_roles, role_permissions
from middleware import check_permission
from flask import g
from app import db
```

## 3. 关键算法设计

### 3.1 角色继承遍历（已在 middleware.py 实现）

```
_collect_role_permissions(role, visited=None):
    visited = {role.id}
    perms = role.permissions 的 code 集合
    if role.parent_role_id:
        parent = Role.query.get(role.parent_role_id)
        if parent and parent.id not in visited:
            perms += _collect_role_permissions(parent, visited)
    return perms
```

### 3.2 继承链循环检测（在 routes_role.py PUT /roles/<id>/permissions 中使用）

```
detect_cycle(role_id, target_parent_id):
    # 检查将 role_id 的 parent 设为 target_parent_id 是否会形成环
    current = target_parent_id
    visited = set()
    while current is not None:
        if current == role_id:
            return True  # 形成环
        if current in visited:
            return False  # 安全（已有 visited 防护）
        visited.add(current)
        role = Role.query.get(current)
        if role:
            current = role.parent_role_id
        else:
            break
    return False
```

### 3.3 文档序列化辅助函数

```python
def _serialize_doc(doc):
    return {
        'id': doc.id,
        'tenant_id': doc.tenant_id,
        'owner_id': doc.owner_id,
        'title': doc.title,
        'content': doc.content
    }
```

### 3.4 角色序列化辅助函数

```python
def _serialize_role(role):
    return {
        'id': role.id,
        'name': role.name,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions]
    }
```

## 4. 实现计划

按依赖顺序执行：

| 顺序 | ATU | 文件 | 复杂度 | 依赖 |
|------|-----|------|--------|------|
| 1 | ATU-003 | routes_auth.py | S | 无（仅依赖已实现的 middleware） |
| 2 | ATU-004 | routes_document.py | M | ATU-003（文档接口需要 JWT 认证流程完整） |
| 3 | ATU-005 | routes_role.py | L | ATU-003（角色接口需要 JWT 认证流程完整） |

ATU-004 和 ATU-005 相互独立，但为保持 Waterfall 严格顺序，先完成 ATU-004 再执行 ATU-005。

## 5. 边界条件和异常处理清单

| 场景 | 处理方式 |
|------|----------|
| 登录请求体不是 JSON | Flask 默认返回 400，需 try/except |
| 登录用户不存在 | 401 |
| 登录密码错误 | 401 |
| 文档标题为空 | 400 |
| 文档不存在 | 404 |
| 跨租户访问文档 | 404 |
| 非文档 owner 且无 write.any | 403 |
| 角色名重复 | 409 |
| parent_role_id 指向不存在角色 | 400 |
| parent_role_id 跨租户 | 400 |
| 继承链循环 | 400 |
| 角色分配跨租户 | 403 |
| 无效权限码 | 400 |
| PUT permissions 部分字段更新 | 不传的字段保持原值 |

## 6. 模块间接口一致性

| 接口 | 值 |
|------|-----|
| 权限码 | `doc.read`, `doc.write`, `doc.delete`, `doc.write.any`, `role.manage` |
| JWT payload | `{user_id: int, tenant_id: int, exp: datetime}` |
| JWT 算法 | HS256 |
| JWT Secret | `current_app.config['JWT_SECRET']` |
| 返回格式 | `{"status": "ok/error", "data": ...}` 或 `{"status": "error", "message": ...}` |
| g.current_user | middleware 装饰器设置的当前用户对象 |
| g.current_permissions | middleware 装饰器设置的权限码集合 |
