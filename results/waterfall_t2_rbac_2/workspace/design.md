# RBAC 权限管理系统 — 方案设计文档

## 1. 设计概述

本文档基于 requirements.md，为三个待实现模块（routes_auth.py、routes_document.py、routes_role.py）提供详细设计规格。models.py 和 middleware.py 已完整实现，本设计直接引用其公开接口。

## 2. 模块依赖关系

```
app.py (不可修改)
  ├── models.py (不可修改) — 数据模型定义
  ├── middleware.py (不可修改) — JWT 验证 + 权限检查
  ├── routes_auth.py (待实现) — 登录
  ├── routes_document.py (待实现) — 文档 CRUD
  └── routes_role.py (待实现) — 角色管理
```

模块间调用关系：
- routes_auth.py → models.User, middleware.hash_password, jwt (pyjwt)
- routes_document.py → models.Document, middleware.check_permission（权限通过 g.current_permissions 获取）
- routes_role.py → models.Role, models.Permission, models.User, models.role_permissions, models.user_roles, middleware.get_current_user, middleware.check_permission, middleware.get_user_permissions, app.db

## 3. 数据库表设计

数据库表已由 models.py 定义，无需修改。关键表结构如下：

### 3.1 role_permissions（多对多关联表）
- role_id (FK → role.id, PK)
- permission_id (FK → permission.id, PK)

### 3.2 user_roles（多对多关联表）
- user_id (FK → user.id, PK)
- role_id (FK → role.id, PK)

## 4. API 端点设计

### 4.1 POST /login（routes_auth.py）

**设计规格**：

```
导入: from flask import Blueprint, request, jsonify
       import jwt as pyjwt
       from datetime import datetime, timedelta
       from flask import current_app
       from models import User
       from middleware import hash_password

路由: @auth_bp.route('/login', methods=['POST'])
```

**处理流程**：
1. 解析请求 JSON，提取 username 和 password
2. 验证：缺少任一字段 → 返回 400 `{"status": "error", "message": "..."}``
3. 查询 User: `User.query.filter_by(username=username).first()`
4. 用户不存在 → 返回 401（与密码错误相同，防止枚举）
5. 验证密码: `hash_password(password) != user.password_hash` → 返回 401
6. 生成 JWT:
   - payload: `{'user_id': user.id, 'tenant_id': user.tenant_id, 'exp': datetime.utcnow() + timedelta(hours=current_app.config['JWT_EXPIRY_HOURS'])}`
   - 使用 `pyjwt.encode(payload, current_app.config['JWT_SECRET'], algorithm='HS256')`
7. 返回 200 `{"status": "ok", "data": {"token": token_str}}`

**边界条件**：
- Content-Type 非 JSON → 请求解析失败时返回 400
- username 为空字符串 → 400
- password 为空字符串 → 400

### 4.2 GET /documents（routes_document.py）

**设计规格**：

```
导入: from flask import Blueprint, request, jsonify, g
       from models import Document
       from middleware import check_permission

路由: @document_bp.route('/documents', methods=['GET'])
装饰: @check_permission('doc.read')
```

**处理流程**：
1. `@check_permission('doc.read')` 装饰器自动验证 JWT 和权限
2. 装饰器将用户设为 `g.current_user`，权限设为 `g.current_permissions`
3. 查询: `Document.query.filter_by(tenant_id=g.current_user.tenant_id).all()`
4. 返回 200 `{"status": "ok", "data": [序列化文档列表]}`

**序列化格式**: `{"id": doc.id, "tenant_id": doc.tenant_id, "owner_id": doc.owner_id, "title": doc.title, "content": doc.content}`

### 4.3 GET /documents/<id>（routes_document.py）

**设计规格**：

```
路由: @document_bp.route('/documents/<int:id>', methods=['GET'])
装饰: @check_permission('doc.read')
```

**处理流程**：
1. `@check_permission('doc.read')` 自动验证
2. 查询: `Document.query.get(id)`
3. 不存在 → 返回 404
4. 检查 tenant: `doc.tenant_id != g.current_user.tenant_id` → 返回 404
5. 返回 200 `{"status": "ok", "data": 序列化文档}`

### 4.4 POST /documents（routes_document.py）

**设计规格**：

```
路由: @document_bp.route('/documents', methods=['POST'])
装饰: @check_permission('doc.write')
```

**处理流程**：
1. `@check_permission('doc.write')` 自动验证
2. 解析请求 JSON，提取 title 和 content
3. 验证 title 非空：缺少 title → 返回 400 `{"status": "error", "message": "title is required"}`
4. 创建文档: `Document(tenant_id=g.current_user.tenant_id, owner_id=g.current_user.id, title=title, content=content or '')`
4. `db.session.add(doc); db.session.commit()`
5. 返回 201 `{"status": "ok", "data": 序列化文档}`

### 4.5 PUT /documents/<id>（routes_document.py）

**设计规格**：

```
路由: @document_bp.route('/documents/<int:id>', methods=['PUT'])
装饰: @check_permission('doc.write')
```

**处理流程**：
1. `@check_permission('doc.write')` 自动验证（确保有 doc.write 基础权限）
2. 查询: `Document.query.get(id)`
3. 不存在 → 返回 404
4. 检查 tenant: `doc.tenant_id != g.current_user.tenant_id` → 返回 404
5. Owner 检查: `doc.owner_id != g.current_user.id` 且 `'doc.write.any' not in g.current_permissions` → 返回 403
6. 更新字段（仅更新请求中提供的字段）
7. `db.session.commit()`
8. 返回 200 `{"status": "ok", "data": 序列化文档}`

**注意**: `@check_permission('doc.write')` 装饰器会将权限集设为 `g.current_permissions`，路由函数体内可访问该变量进行额外检查。

### 4.6 DELETE /documents/<id>（routes_document.py）

**设计规格**：

```
路由: @document_bp.route('/documents/<int:id>', methods=['DELETE'])
装饰: @check_permission('doc.delete')
```

**处理流程**：
1. `@check_permission('doc.delete')` 自动验证
2. 查询: `Document.query.get(id)`
3. 不存在 → 返回 404
4. 检查 tenant: `doc.tenant_id != g.current_user.tenant_id` → 返回 404
5. 不检查 owner（有 doc.delete 权限即可删除同 tenant 内任意文档）
6. `db.session.delete(doc); db.session.commit()`
7. 返回 200 `{"status": "ok", "data": 序列化文档}`

### 4.7 POST /roles（routes_role.py）

**设计规格**：

```
导入: from flask import Blueprint, request, jsonify, g
       from models import Role, Permission, role_permissions
       from middleware import check_permission
       from app import db

路由: @role_bp.route('/roles', methods=['POST'])
装饰: @check_permission('role.manage')
```

**处理流程**：
1. `@check_permission('role.manage')` 自动验证
2. 解析请求 JSON，提取 name, parent_role_id, permissions
3. 验证 name 非空
4. 检查同 tenant 角色名重复: `Role.query.filter_by(tenant_id=g.current_user.tenant_id, name=name).first()`
5. 重复 → 返回 409
6. 如果提供 parent_role_id:
   - 查询 parent role: `Role.query.get(parent_role_id)`
   - 不存在 → 返回 400
   - 不同 tenant → 返回 404（不泄露存在性）
7. 创建 Role: `Role(tenant_id=g.current_user.tenant_id, name=name, parent_role_id=parent_role_id)`
8. 关联 permissions:
   - 遍历 permissions 列表中的 code 字符串
   - 查询 `Permission.query.filter(Permission.code.in_(permissions)).all()`
   - 设置 `role.permissions = queried_permissions`
9. `db.session.add(role); db.session.commit()`
10. 返回 201 `{"status": "ok", "data": {序列化角色}}`

**序列化格式**: `{"id": role.id, "name": role.name, "parent_role_id": role.parent_role_id, "permissions": [p.code for p in role.permissions]}`

### 4.8 GET /roles（routes_role.py）

**设计规格**：

```
路由: @role_bp.route('/roles', methods=['GET'])
装饰: @check_permission('role.manage')
```

**处理流程**：
1. `@check_permission('role.manage')` 自动验证
2. 查询: `Role.query.filter_by(tenant_id=g.current_user.tenant_id).all()`
3. 返回 200 `{"status": "ok", "data": [序列化角色列表]}`

### 4.9 PUT /roles/<id>/permissions（routes_role.py）

**设计规格**：

```
路由: @role_bp.route('/roles/<int:id>/permissions', methods=['PUT'])
装饰: @check_permission('role.manage')
```

**处理流程**：
1. `@check_permission('role.manage')` 自动验证
2. 查询目标角色: `Role.query.get(id)`
3. 不存在 → 返回 404
3.5. **Tenant 隔离检查**: `role.tenant_id != g.current_user.tenant_id` → 返回 404（不泄露存在性）
4. 解析请求 JSON，提取 permissions 和 parent_role_id
5. 如果提供 parent_role_id:
   - 如果 `parent_role_id == id`（自己指向自己）→ 返回 400（循环）
   - 查询 parent role，不存在或不同 tenant → 返回 400
   - **循环检测**: 从 parent_role 沿 parent_role_id 链向上遍历，如果遇到当前角色 id → 返回 400
6. 全量替换 permissions（替换语义）:
   - 查询 `Permission.query.filter(Permission.code.in_(new_permissions)).all()`
   - 设置 `role.permissions = new_permission_objects`
7. 如果提供 parent_role_id: `role.parent_role_id = parent_role_id`
8. `db.session.commit()`
9. 返回 200 `{"status": "ok", "data": 序列化角色}`

**循环检测算法**:
```python
def _has_cycle(role_id, target_parent_id):
    """检查从 target_parent_id 沿继承链向上是否会回到 role_id"""
    visited = set()
    current = target_parent_id
    while current is not None:
        if current == role_id:
            return True
        if current in visited:
            return True  # 已存在的循环
        visited.add(current)
        role = Role.query.get(current)
        if role is None:
            return False
        current = role.parent_role_id
    return False
```

### 4.10 POST /users/<id>/roles（routes_role.py）

**设计规格**：

```
路由: @role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
装饰: @check_permission('role.manage')
```

**处理流程**：
1. `@check_permission('role.manage')` 自动验证
2. 查询目标用户: `User.query.get(user_id)`
3. 不存在 → 返回 404
4. 解析请求 JSON，提取 role_id
5. 查询目标角色: `Role.query.get(role_id)`
6. 不存在 → 返回 404
7. 租户检查: `user.tenant_id != g.current_user.tenant_id` 或 `role.tenant_id != g.current_user.tenant_id` → 返回 404
8. 添加角色: `user.roles.append(role)`
9. `db.session.commit()`
10. 返回 200 `{"status": "ok", "data": {"user_id": user.id, "role_id": role.id}}`

### 4.11 DELETE /users/<id>/roles/<role_id>（routes_role.py）

**设计规格**：

```
路由: @role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
装饰: @check_permission('role.manage')
```

**处理流程**：
1. `@check_permission('role.manage')` 自动验证
2. 查询目标用户: `User.query.get(user_id)`
3. 不存在 → 返回 404
3.5. **Tenant 隔离检查**: `user.tenant_id != g.current_user.tenant_id` → 返回 404（不泄露存在性）
4. 查询目标角色: `Role.query.get(role_id)`
5. 如果角色在用户的角色列表中: `user.roles.remove(role)`
6. **幂等**: 角色不在列表中时不报错
7. `db.session.commit()`
8. 返回 200 `{"status": "ok", "data": {"user_id": user.id, "role_id": role_id}}`

## 5. 关键算法逻辑

### 5.1 继承链循环检测

当设置角色的 parent_role_id 时，需要检测是否会形成循环。算法：从拟议的父角色出发，沿 parent_role_id 链向上遍历，如果遇到当前角色 ID，则存在循环。

**场景**: 角色 A → 角色 B → 角色 A（循环）
- 尝试设置 A.parent = B 时，B 的 parent 已经是 A → 循环

### 5.2 权限继承

已由 middleware.py 的 `_collect_role_permissions()` 实现，递归向上收集权限。本设计无需额外实现。

### 5.3 文档序列化

统一序列化函数，确保所有文档接口返回一致的 JSON 结构：

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

### 5.4 角色序列化

```python
def _serialize_role(role):
    return {
        'id': role.id,
        'name': role.name,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions]
    }
```

## 6. 实现计划（ATU 拆分和执行顺序）

### ATU-003: routes_auth.py（复杂度 S，~30 行）

**实现范围**: 仅 POST /login
**依赖**: middleware.hash_password, models.User, pyjwt, flask.current_app
**执行顺序**: 第 1 个实现（其他模块依赖登录获取 token）

### ATU-004: routes_document.py（复杂度 M，~80 行）

**实现范围**: 5 个文档端点
**依赖**: middleware.check_permission, middleware.get_user_permissions, models.Document, app.db
**关键点**: PUT 端点需要在装饰器之外做额外的 owner/write.any 检查
**执行顺序**: 第 2 个实现

### ATU-005: routes_role.py（复杂度 M，~90 行）

**实现范围**: 5 个角色管理端点
**依赖**: middleware.check_permission, middleware.get_user_permissions, models.Role/Permission/User, app.db
**关键点**: 循环检测算法、全量替换语义、幂等删除
**执行顺序**: 第 3 个实现

### 实现顺序理由

1. routes_auth.py 最先（其他所有测试依赖登录获取 JWT token）
2. routes_document.py 次之（文档 CRUD 是核心业务逻辑）
3. routes_role.py 最后（角色管理涉及复杂的循环检测逻辑，但可以独立测试）

## 7. 测试策略

### 测试执行命令
```bash
cd starter && pip install -r requirements.txt && cd .. && python -m pytest tests/ -v
```

### 测试覆盖范围（test_basic.py 19 个测试）
- TestAuth (3): 认证拦截
- TestRoleManagement (4): 角色创建、权限检查、继承、循环检测
- TestDocumentRBAC (6): 文档读写权限、owner 检查、write.any
- TestMultiTenant (3): 跨 tenant 隔离
- TestPermissionInheritance (3): 权限继承传递、移除、多角色并集
