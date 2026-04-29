# 方案设计文档 — T2-3 RBAC 权限管理系统

## 1. 系统架构

```
┌──────────────────────────────────────────────────────┐
│                      app.py                          │
│            (Flask App Factory, 不可修改)               │
│                                                      │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ auth_bp  │  │ document_bp  │  │   role_bp    │   │
│  │(routes_  │  │(routes_      │  │(routes_      │   │
│  │ auth.py) │  │document.py)  │  │role.py)      │   │
│  └────┬─────┘  └──────┬───────┘  └──────┬───────┘   │
│       │               │                  │           │
│       └───────────────┼──────────────────┘           │
│                       ▼                              │
│              ┌─────────────────┐                     │
│              │  middleware.py   │                     │
│              │  JWT + 权限检查   │                     │
│              └────────┬────────┘                     │
│                       ▼                              │
│              ┌─────────────────┐                     │
│              │   models.py     │                     │
│              │  SQLAlchemy ORM │                     │
│              └─────────────────┘                     │
└──────────────────────────────────────────────────────┘
```

## 2. 模块间依赖关系

| 模块 | 导入来源 | 导出 |
|------|---------|------|
| `app.py` | `models.py`, `routes_auth.py`, `routes_document.py`, `routes_role.py` | `db`, `create_app()` |
| `models.py` | `app.db` | `Tenant`, `User`, `Role`, `Permission`, `Document`, `role_permissions`, `user_roles` |
| `middleware.py` | `models.*`, `app.db` | `hash_password()`, `get_current_user()`, `get_user_permissions()`, `check_permission()`, `require_auth()` |
| `routes_auth.py` | `flask`, `middleware.*`, `models.*` | `auth_bp` |
| `routes_document.py` | `flask`, `middleware.*`, `models.*`, `app.db` | `document_bp` |
| `routes_role.py` | `flask`, `middleware.*`, `models.*`, `app.db` | `role_bp` |

## 3. API 端点详细设计

### 3.1 POST /login (routes_auth.py)

**实现规格**:
```python
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    # 1. 验证请求体：username 和 password 不能为空
    # 2. 查询 User by username
    # 3. 比对 hash_password(password) == user.password_hash
    # 4. 生成 JWT: payload = {"user_id": user.id, "tenant_id": user.tenant_id, "exp": ...}
    # 5. 返回 {"status": "ok", "data": {"token": token}}
```

**错误码映射**:
| 条件 | HTTP 状态码 | 响应 |
|------|------------|------|
| 缺少 username 或 password | 400 | `{"status": "error", "message": "..."}` |
| 用户不存在或密码错误 | 401 | `{"status": "error", "message": "Invalid credentials"}` |
| 成功 | 200 | `{"status": "ok", "data": {"token": "..."}}` |

### 3.2 GET /documents (routes_document.py)

**实现规格**:
```python
@document_bp.route('/documents', methods=['GET'])
@check_permission('doc.read')
def list_documents():
    # 1. g.current_user 已由装饰器设置
    # 2. 查询: Document.query.filter_by(tenant_id=g.current_user.tenant_id).all()
    # 3. 序列化为 JSON 列表返回
```

### 3.3 GET /documents/<id> (routes_document.py)

**实现规格**:
```python
@document_bp.route('/documents/<int:doc_id>', methods=['GET'])
@check_permission('doc.read')
def get_document(doc_id):
    # 1. 查询 Document by id
    # 2. 如果不存在 → 404
    # 3. 如果 document.tenant_id != user.tenant_id → 404（隐藏存在性）
    # 4. 返回文档详情
```

### 3.4 POST /documents (routes_document.py)

**实现规格**:
```python
@document_bp.route('/documents', methods=['POST'])
@check_permission('doc.write')
def create_document():
    # 1. 从请求体获取 title 和 content
    # 2. 创建 Document(tenant_id=user.tenant_id, owner_id=user.id, ...)
    # 3. db.session.add() + db.session.commit()
    # 4. 返回 201 + 文档数据
```

### 3.5 PUT /documents/<id> (routes_document.py)

**实现规格**:
```python
@document_bp.route('/documents/<int:doc_id>', methods=['PUT'])
@check_permission('doc.write')
def update_document(doc_id):
    # 1. 查询 Document by id
    # 2. 如果不存在或不同 tenant → 404
    # 3. 检查权限：
    #    - document.owner_id == user.id（是 owner）→ 允许
    #    - 'doc.write.any' in g.current_permissions → 允许
    #    - 否则 → 403
    # 4. 更新 title/content（只更新请求体中提供的字段）
    # 5. 返回更新后的文档
```

### 3.6 DELETE /documents/<id> (routes_document.py)

**实现规格**:
```python
@document_bp.route('/documents/<int:doc_id>', methods=['DELETE'])
@check_permission('doc.delete')
def delete_document(doc_id):
    # 1. 查询 Document by id
    # 2. 如果不存在或不同 tenant → 404
    # 3. db.session.delete() + db.session.commit()
    # 4. 返回 {"status": "ok", "data": null}
```

### 3.7 POST /roles (routes_role.py)

**实现规格**:
```python
@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    # 1. 获取 name, permissions, parent_role_id（可选）
    # 2. 验证 name 非空
    # 3. 检查同 tenant 内角色名唯一性（重复 → 409）
    # 4. 如果 parent_role_id 提供：
    #    - 查询 Role by id，不存在或不同 tenant → 400
    # 5. 查询 permissions 中每个 code 对应的 Permission 记录
    # 6. 创建 Role，设置 role.permissions
    # 7. 返回 201 + 角色数据（含 permissions code 列表）
```

### 3.8 GET /roles (routes_role.py)

**实现规格**:
```python
@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    # 1. 查询 Role.query.filter_by(tenant_id=user.tenant_id).all()
    # 2. 序列化每个角色：{"id", "name", "parent_role_id", "permissions": [code, ...]}
    # 3. 返回列表
```

### 3.9 PUT /roles/<id>/permissions (routes_role.py)

**实现规格**:
```python
@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(role_id):
    # 1. 查询 Role by id，不存在 → 404
    # 2. 获取 permissions（可选）和 parent_role_id（可选）
    # 3. 如果提供了 parent_role_id：
    #    - 查询父角色，不存在或不同 tenant → 400
    #    - 循环检测：检查 parent_role_id 的继承链中是否包含当前 role_id
    #      实现方式：从 parent_role_id 开始沿 parent_role_id 向上遍历，
    #      如果遇到当前 role_id 则存在循环 → 400
    # 4. 如果提供了 permissions：
    #    - 查询对应的 Permission 记录
    #    - 替换 role.permissions
    # 5. 返回更新后的角色数据
```

### 3.10 POST /users/<id>/roles (routes_role.py)

**实现规格**:
```python
@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role(user_id):
    # 1. 查询 User by id，不存在 → 404
    # 2. 查询 Role by role_id，不存在 → 404
    # 3. 检查 user.tenant_id == role.tenant_id，不同 → 403
    # 4. 如果角色未分配给该用户：user.roles.append(role)
    # 5. db.session.commit()
    # 6. 返回 {"status": "ok", "data": null}
```

### 3.11 DELETE /users/<id>/roles/<role_id> (routes_role.py)

**实现规格**:
```python
@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role(user_id, role_id):
    # 1. 查询 User by id，不存在 → 404
    # 2. 如果角色已分配给该用户：user.roles.remove(role)
    # 3. 如果角色未分配：直接返回成功（幂等）
    # 4. role_id 对应的角色不存在：也返回成功（幂等）
    # 5. db.session.commit()
    # 6. 返回 {"status": "ok", "data": null}
```

## 4. 关键算法设计

### 4.1 继承链循环检测算法

用于 PUT /roles/<id>/permissions 中设置 parent_role_id 时：

```python
def _would_create_cycle(role_id, new_parent_id):
    """检查将 role_id 的父角色设为 new_parent_id 是否会产生循环。"""
    visited = {role_id}
    current = new_parent_id
    while current is not None:
        if current in visited:
            return True  # 循环！
        visited.add(current)
        role = Role.query.get(current)
        if role is None:
            return False  # 链断裂，无循环
        current = role.parent_role_id
    return False
```

**算法说明**：
- 从新父角色 `new_parent_id` 开始，沿 `parent_role_id` 向上遍历
- 如果遍历过程中遇到 `role_id`（当前角色），说明形成循环
- 使用 `visited` 集合检测循环，同时处理非树形链路

### 4.2 文档序列化辅助函数

```python
def _serialize_document(doc):
    return {
        "id": doc.id,
        "tenant_id": doc.tenant_id,
        "owner_id": doc.owner_id,
        "title": doc.title,
        "content": doc.content
    }
```

### 4.3 角色序列化辅助函数

```python
def _serialize_role(role):
    return {
        "id": role.id,
        "name": role.name,
        "parent_role_id": role.parent_role_id,
        "permissions": [p.code for p in role.permissions]
    }
```

## 5. 实现计划

### ATU 执行顺序

| 顺序 | ATU ID | 描述 | 文件 | 复杂度 |
|------|--------|------|------|--------|
| 1 | ATU-003 | 认证接口 | `routes_auth.py` | S |
| 2 | ATU-004 | 文档接口 | `routes_document.py` | L |
| 3 | ATU-005 | 角色管理接口 | `routes_role.py` | L |

### 各 ATU 实现要点

#### ATU-003: routes_auth.py
- 仅需实现 `POST /login` 一个端点
- 导入 `middleware.hash_password` 和 `models.User`
- 使用 `pyjwt.encode` 生成 JWT
- JWT 过期时间从 `current_app.config['JWT_EXPIRY_HOURS']` 获取
- 预估代码量：~20 行

#### ATU-004: routes_document.py
- 实现 5 个端点
- 所有端点使用 `@check_permission()` 装饰器
- GET 端点使用 `@check_permission('doc.read')`
- POST 使用 `@check_permission('doc.write')`
- PUT 额外检查 owner 或 `doc.write.any`
- DELETE 使用 `@check_permission('doc.delete')`
- 预估代码量：~80 行

#### ATU-005: routes_role.py
- 实现 5 个端点
- 所有端点使用 `@check_permission('role.manage')`
- POST /roles 需处理角色名唯一性检查
- PUT /roles/<id>/permissions 需实现循环检测算法
- POST /users/<id>/roles 和 DELETE 需处理跨租户检查和幂等性
- 预估代码量：~100 行

## 6. 数据流示例

### 登录 → 创建文档 → 编辑文档
```
Client                  Server
  │                       │
  │ POST /login           │
  │ {username, password}  │
  │──────────────────────▶│ 验证 → 生成 JWT
  │                       │
  │ 200 {token}           │
  │◀──────────────────────│
  │                       │
  │ GET /documents        │
  │ Bearer <token>        │
  │──────────────────────▶│ JWT 验证 → 权限检查(doc.read) → 查询
  │                       │
  │ 200 {data: [...]}     │
  │◀──────────────────────│
  │                       │
  │ POST /documents       │
  │ {title, content}      │
  │──────────────────────▶│ JWT → doc.write → 创建
  │                       │
  │ 201 {data: {doc}}     │
  │◀──────────────────────│
```

## 7. 设计约束

1. **不可修改的文件**：`app.py`（Flask app 工厂）
2. **已完成的模块**：`models.py`、`middleware.py`（直接使用，不修改）
3. **Blueprint 名称固定**：`auth_bp`、`document_bp`、`role_bp`
4. **JWT Secret**：从 `current_app.config['JWT_SECRET']` 获取
5. **数据库**：SQLite，使用 Flask-SQLAlchemy ORM
6. **响应格式**：`{"status": "ok/error", "data/message": ...}`
