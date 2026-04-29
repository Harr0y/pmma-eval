# T2-3：RBAC 权限管理系统（多模块版本）

## 项目结构

```
starter/
  app.py              # Flask app 工厂 + DB 初始化（请勿修改）
  models.py           # 数据模型（Tenant, User, Role, Permission, Document + 关联表）
  middleware.py       # JWT 验证 + 权限检查（含继承遍历）
  routes_auth.py      # 登录接口 —— 需要完善
  routes_document.py  # 文档 CRUD + RBAC —— 需要实现
  routes_role.py      # 角色管理 + 用户角色分配 —— 需要实现
  requirements.txt    # 依赖
```

## 重要提示

这是一个**多模块项目**，代码分布在 6 个文件中。模块间有复杂依赖：
- `middleware.py` 需要从 `models.py` 导入 Role/Permission 进行继承遍历
- `routes_document.py` 需要使用 `middleware.py` 的权限检查
- `routes_role.py` 需要检查 `middleware.py` 的 role.manage 权限
- 所有路由需要从 `models.py` 导入对应模型
- `app.py` 负责组装所有模块（请勿修改）

**请确保各模块之间的接口（权限码字符串、模型字段名、JWT payload 结构）保持一致。**

## 功能要求

### 1. 数据模型（models.py）
- Tenant: id, name
- User: id, tenant_id (FK), username (unique), password_hash, created_at
- Role: id, tenant_id (FK), name, parent_role_id (self-ref FK, nullable)
- Permission: id, code (e.g. `doc.read`, `doc.write`, `doc.delete`, `doc.write.any`, `role.manage`)
- role_permissions: 多对多关联表
- user_roles: 多对多关联表
- Document: id, tenant_id (FK), owner_id (FK), title, content

### 2. 认证中间件（middleware.py）
- JWT 验证：从 `Authorization: Bearer <token>` 解析
- 缺失/无效/过期 token → 401
- 权限检查：沿 `parent_role_id` 继承链向上查找
- 提供装饰器和辅助函数

### 3. 认证接口（routes_auth.py）
使用 `auth_bp = Blueprint('auth_bp', __name__)`
- `POST /login` — 登录，返回 JWT（含 user_id + tenant_id）

### 4. 文档接口（routes_document.py）
使用 `document_bp = Blueprint('document_bp', __name__)`
- `GET /documents` — 需要 `doc.read`，只返回本 tenant
- `GET /documents/<id>` — 需要 `doc.read` + 同 tenant（否则 404）
- `POST /documents` — 需要 `doc.write`
- `PUT /documents/<id>` — 需要 `doc.write` +（owner 或 `doc.write.any`）
- `DELETE /documents/<id>` — 需要 `doc.delete`

### 5. 角色管理接口（routes_role.py）
使用 `role_bp = Blueprint('role_bp', __name__)`
- `POST /roles` — 创建角色（需要 `role.manage`）
- `GET /roles` — 列出本 tenant 的角色
- `PUT /roles/<id>/permissions` — 替换权限集 + 更新 parent
- `POST /users/<id>/roles` — 分配角色
- `DELETE /users/<id>/roles/<role_id>` — 移除角色
- 创建/修改时检测继承链循环

### 接口返回格式

```json
{"status": "ok", "data": ...}
{"status": "error", "message": "错误描述"}
```

## 验收标准

1. ✅ 所有上述 API 接口可正常调用
2. ✅ `tests/test_basic.py` 中的所有测试用例通过

## 测试

```bash
cd starter && pip install -r requirements.txt && cd .. && python -m pytest tests/ -v
```
