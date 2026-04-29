# Design — T2-3 RBAC 权限管理系统

## 1. 架构总览

```
app.py (不可修改 — 工厂 + Blueprint 注册)
  ├── models.py (不可修改 — 数据模型)
  ├── middleware.py (不可修改 — JWT + 权限检查)
  ├── routes_auth.py (ATU-003 — 认证)
  ├── routes_document.py (ATU-004 — 文档 CRUD)
  └── routes_role.py (ATU-005 — 角色管理)
```

所有 3 个路由模块作为 Flask Blueprint 注册，共享 `middleware.py` 提供的认证和权限基础设施。

## 2. 实现计划与 ATU 拆分

按顺序执行：ATU-003 → ATU-004 → ATU-005（严格顺序，后者依赖前者通过测试）

## 3. ATU-003: routes_auth.py 详细设计

### 文件：`starter/routes_auth.py`

#### 导入依赖
```python
from flask import Blueprint, request, jsonify, current_app
import jwt as pyjwt
import datetime
from models import User
from middleware import hash_password
```

#### POST /login 实现

```
1. 从 request.json 获取 username 和 password
2. 验证：如果缺少 username 或 password → return 400
3. 查询 User.query.filter_by(username=username).first()
4. 如果用户不存在 → return 401
5. 使用 hash_password(password) 与 user.password_hash 比较
6. 如果不匹配 → return 401
7. 生成 JWT：
   payload = {
     'user_id': user.id,
     'tenant_id': user.tenant_id,
     'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=app.config['JWT_EXPIRY_HOURS'])
   }
   token = pyjwt.encode(payload, app.config['JWT_SECRET'], algorithm='HS256')
8. return {"status": "ok", "data": {"token": token}}, 200
```

**边界条件**：
- request.json 为 None（非 JSON 请求）→ 400
- username 为空字符串 → 400
- password 为空字符串 → 400

## 4. ATU-004: routes_document.py 详细设计

### 文件：`starter/routes_document.py`

#### 导入依赖
```python
from flask import Blueprint, request, jsonify, g
from models import Document
from middleware import check_permission, get_current_user, get_user_permissions
from app import db
```

#### GET /documents — 列出文档
```
@document_bp.route('/documents', methods=['GET'])
@check_permission('doc.read')
def list_documents():
    user = g.current_user
    docs = Document.query.filter_by(tenant_id=user.tenant_id).all()
    return {"status": "ok", "data": [
        {"id": d.id, "tenant_id": d.tenant_id, "owner_id": d.owner_id,
         "title": d.title, "content": d.content}
        for d in docs
    ]}
```

#### GET /documents/<id> — 获取单个文档
```
@document_bp.route('/documents/<int:id>', methods=['GET'])
@check_permission('doc.read')
def get_document(id):
    user = g.current_user
    doc = Document.query.get(id)
    if doc is None or doc.tenant_id != user.tenant_id:
        return {"status": "error", "message": "Not found"}, 404
    return {"status": "ok", "data": {...}}
```

#### POST /documents — 创建文档
```
@document_bp.route('/documents', methods=['POST'])
@check_permission('doc.write')
def create_document():
    user = g.current_user
    data = request.json
    doc = Document(tenant_id=user.tenant_id, owner_id=user.id,
                   title=data['title'], content=data.get('content', ''))
    db.session.add(doc)
    db.session.commit()
    return {"status": "ok", "data": {...}}, 201
```

#### PUT /documents/<id> — 更新文档
```
@document_bp.route('/documents/<int:id>', methods=['PUT'])
@check_permission('doc.write')
def update_document(id):
    user = g.current_user
    perms = g.current_permissions
    doc = Document.query.get(id)
    if doc is None or doc.tenant_id != user.tenant_id:
        return {"status": "error", "message": "Not found"}, 404
    if doc.owner_id != user.id and 'doc.write.any' not in perms:
        return {"status": "error", "message": "Permission denied"}, 403
    # 更新字段
    data = request.json
    doc.title = data.get('title', doc.title)
    doc.content = data.get('content', doc.content)
    db.session.commit()
    return {"status": "ok", "data": {...}}
```

#### DELETE /documents/<id> — 删除文档
```
@document_bp.route('/documents/<int:id>', methods=['DELETE'])
@check_permission('doc.delete')
def delete_document(id):
    user = g.current_user
    doc = Document.query.get(id)
    if doc is None or doc.tenant_id != user.tenant_id:
        return {"status": "error", "message": "Not found"}, 404
    db.session.delete(doc)
    db.session.commit()
    return {"status": "ok", "data": {"id": doc.id}}
```

## 5. ATU-005: routes_role.py 详细设计

### 文件：`starter/routes_role.py`

#### 导入依赖
```python
from flask import Blueprint, request, jsonify, g
from models import Role, Permission, User, user_roles, role_permissions
from middleware import check_permission
from app import db
```

#### POST /roles — 创建角色
```
@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    user = g.current_user
    data = request.json
    name = data.get('name')
    if not name:
        return {"status": "error", "message": "Name is required"}, 400

    # 检查同租户角色名唯一性
    existing = Role.query.filter_by(tenant_id=user.tenant_id, name=name).first()
    if existing:
        return {"status": "error", "message": "Role name already exists"}, 409

    # 验证 parent_role_id 属于同租户
    parent_id = data.get('parent_role_id')
    if parent_id is not None:
        parent = Role.query.get(parent_id)
        if parent is None or parent.tenant_id != user.tenant_id:
            return {"status": "error", "message": "Invalid parent role"}, 400

    # 创建角色
    role = Role(tenant_id=user.tenant_id, name=name, parent_role_id=parent_id)
    db.session.add(role)
    db.session.flush()  # 获取 role.id

    # 关联权限（通过 Permission.code 查找）
    perm_codes = data.get('permissions', [])
    for code in perm_codes:
        perm = Permission.query.filter_by(code=code).first()
        if perm:
            role.permissions.append(perm)

    db.session.commit()
    return {"status": "ok", "data": {
        "id": role.id, "name": role.name,
        "parent_role_id": role.parent_role_id,
        "permissions": [p.code for p in role.permissions]
    }}, 201
```

#### GET /roles — 列出本租户角色
```
@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    user = g.current_user
    roles = Role.query.filter_by(tenant_id=user.tenant_id).all()
    return {"status": "ok", "data": [
        {"id": r.id, "name": r.name, "parent_role_id": r.parent_role_id,
         "permissions": [p.code for p in r.permissions]}
        for r in roles
    ]}
```

#### PUT /roles/<id>/permissions — 更新权限和父角色
```
@role_bp.route('/roles/<int:id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(id):
    user = g.current_user
    role = Role.query.get(id)
    if role is None or role.tenant_id != user.tenant_id:
        return {"status": "error", "message": "Role not found"}, 404

    data = request.json

    # 验证并设置 parent_role_id
    parent_id = data.get('parent_role_id')
    if parent_id is not None:
        parent = Role.query.get(parent_id)
        if parent is None or parent.tenant_id != user.tenant_id:
            return {"status": "error", "message": "Invalid parent role"}, 400
        # 循环检测
        if _would_create_cycle(role.id, parent_id):
            return {"status": "error", "message": "Inheritance cycle detected"}, 400
    role.parent_role_id = parent_id

    # 替换权限集
    role.permissions = []
    perm_codes = data.get('permissions', [])
    for code in perm_codes:
        perm = Permission.query.filter_by(code=code).first()
        if perm:
            role.permissions.append(perm)

    db.session.commit()
    return {"status": "ok", "data": {
        "id": role.id, "name": role.name,
        "parent_role_id": role.parent_role_id,
        "permissions": [p.code for p in role.permissions]
    }}
```

#### POST /users/<id>/roles — 分配角色
```
@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role(user_id):
    current = g.current_user
    target_user = User.query.get(user_id)
    if target_user is None or target_user.tenant_id != current.tenant_id:
        return {"status": "error", "message": "User not found"}, 404

    data = request.json
    role = Role.query.get(data.get('role_id'))
    if role is None or role.tenant_id != current.tenant_id:
        return {"status": "error", "message": "Role not found"}, 404

    # 避免重复分配
    if role not in target_user.roles:
        target_user.roles.append(role)
        db.session.commit()

    return {"status": "ok", "data": {"user_id": user_id, "role_id": role.id}}
```

#### DELETE /users/<id>/roles/<role_id> — 移除角色
```
@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role(user_id, role_id):
    current = g.current_user
    target_user = User.query.get(user_id)
    if target_user is None or target_user.tenant_id != current.tenant_id:
        return {"status": "error", "message": "User not found"}, 404

    role = Role.query.get(role_id)
    if role and role in target_user.roles:
        target_user.roles.remove(role)
        db.session.commit()

    # 幂等：角色未分配时也不报错
    return {"status": "ok", "data": {"user_id": user_id, "role_id": role_id}}
```

### 关键算法：继承链循环检测

```python
def _would_create_cycle(role_id, new_parent_id):
    """检查将 role_id 的 parent 设为 new_parent_id 是否会形成环。

    算法：从 new_parent_id 开始，沿 parent_role_id 向上遍历。
    如果在遍历过程中遇到 role_id，则说明会形成环。

    例：A → B → C（C 的 parent 是 B）
    如果要将 B 的 parent 设为 C，则从 C 向上遍历：C → B → ... → 会遇到 B（即 role_id）
    因此会形成环：B → C → B

    Returns:
        True: 会形成环
        False: 不会形成环
    """
    visited = set()
    current = new_parent_id
    while current is not None:
        if current == role_id:
            return True
        if current in visited:
            return True  # 已有环（防御性检查）
        visited.add(current)
        parent_role = Role.query.get(current)
        if parent_role is None:
            break
        current = parent_role.parent_role_id
    return False
```

## 6. 统一响应格式

所有端点返回格式：
- 成功：`{"status": "ok", "data": ...}`
- 失败：`{"status": "error", "message": "错误描述"}`

## 7. Reviewer 非阻塞建议的处理

| 建议 | 处理方式 |
|------|---------|
| FR-ROLE-4 跨租户角色分配错误码应同时允许 403/404 | 在设计中通过 tenant_id 检查实现：target_user 不属于同 tenant → 404，role 不属于同 tenant → 404。测试允许 403 或 404，均满足 |
| DELETE 成功响应码未明确 | 设计为返回 200 + `{"status": "ok", "data": {"id": ...}}` |

## 8. 风险与注意事项

- **模块间导入顺序**：routes_*.py 中的 `from models import ...` 和 `from middleware import ...` 依赖 app.py 已初始化 db，这在 Blueprint 注册时由 Flask 延迟导入机制保证
- **权限码字符串一致性**：所有模块使用相同的权限码字符串常量（`doc.read`, `doc.write`, `doc.delete`, `doc.write.any`, `role.manage`）
- **JWT payload 结构**：必须包含 `user_id` 和 `tenant_id`，这是 middleware.get_current_user() 和所有租户隔离逻辑的基础
