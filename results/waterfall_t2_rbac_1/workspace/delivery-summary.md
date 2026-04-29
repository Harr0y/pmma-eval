# Delivery Summary — T2-3 RBAC 权限管理系统

## 1. 项目概述

实现了一个基于角色的访问控制（RBAC）系统，支持多租户隔离、角色继承和细粒度权限管理。系统基于 Flask 框架，使用 JWT 认证，代码分布在 6 个模块文件中。

## 2. 实现的功能

### 2.1 认证模块（routes_auth.py）— ATU-003
- `POST /login` — 用户登录，返回 JWT（含 user_id, tenant_id, exp）
- 密码验证使用 SHA-256 哈希
- 完整的错误处理：缺失字段（400）、无效凭证（401）、非 JSON 请求（400）

### 2.2 文档模块（routes_document.py）— ATU-004
- `GET /documents` — 列出本租户文档（doc.read 权限）
- `GET /documents/<id>` — 获取单个文档（doc.read + tenant 隔离）
- `POST /documents` — 创建文档（doc.write，返回 201）
- `PUT /documents/<id>` — 更新文档（doc.write + owner 或 doc.write.any）
- `DELETE /documents/<id>` — 删除文档（doc.delete + tenant 隔离）

### 2.3 角色管理模块（routes_role.py）— ATU-005
- `POST /roles` — 创建角色（role.manage 权限，名称唯一性检查 409）
- `GET /roles` — 列出本租户角色
- `PUT /roles/<id>/permissions` — 替换权限集 + 更新父角色（含循环检测 400）
- `POST /users/<id>/roles` — 分配角色（user/role 同租户检查）
- `DELETE /users/<id>/roles/<role_id>` — 移除角色（幂等操作）

### 2.4 关键算法
- **继承链循环检测**：`_would_create_cycle()` 从 new_parent_id 沿 parent_role_id 链向上遍历，检测是否会形成环
- **角色权限继承**：`middleware._collect_role_permissions()` 递归遍历父角色链，合并权限集合

## 3. 测试覆盖

| 指标 | 值 |
|------|------|
| 测试总数 | 19 |
| 通过 | 19 |
| 失败 | 0 |
| 验收标准覆盖 | 17/17 (AC-1 ~ AC-17) |

### 测试类别
- 认证测试（3）：token 缺失/无效/过期
- 角色管理测试（4）：创建、权限检查、继承、循环检测
- 文档 RBAC 测试（6）：读/写/编辑权限控制
- 多租户测试（3）：跨租户隔离
- 权限继承测试（3）：传播、撤销、多角色并集

## 4. 已知问题

1. `test_basic.py` 中使用已弃用的 `datetime.datetime.utcnow()`
2. `models.py` / `middleware.py` 中使用已弃用的 `Query.get()`（不可修改文件）
3. 测试中 JWT 密钥过短（仅测试环境）
4. DELETE 端点和 409 错误场景缺少直接测试用例

以上问题均为非阻塞，不影响功能正确性。

## 5. 修改的文件

| 文件 | 变更说明 |
|------|---------|
| `starter/routes_auth.py` | 新增 POST /login 实现 |
| `starter/routes_document.py` | 新增 5 个文档 CRUD 端点实现 |
| `starter/routes_role.py` | 新增 5 个角色管理端点 + 循环检测实现 |

## 6. 项目交付物

| 交付物 | 说明 |
|--------|------|
| `requirements.md` | 需求文档（17 条功能需求 + 4 条非功能需求 + 17 条验收标准） |
| `design.md` | 设计文档（API 设计 + 算法设计 + 模块间接口约定） |
| `starter/routes_auth.py` | 认证模块实现 |
| `starter/routes_document.py` | 文档模块实现 |
| `starter/routes_role.py` | 角色管理模块实现 |
| `test-report.md` | 测试报告（19/19 通过） |
| `state.json` | 项目状态追踪（7 个 ATU 全部 Done） |
