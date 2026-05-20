# 交付总结 — T2-3 RBAC 权限管理系统

## 1. 项目概述

基于 Flask 的多租户 RBAC 权限管理系统，支持角色继承、权限代码、租户隔离。采用瀑布式项目管理方法，严格按阶段推进。

## 2. 实现的功能

### 2.1 认证接口（routes_auth.py）
- **POST /login** — 用户登录，验证用户名密码，返回 JWT（含 user_id, tenant_id, exp）
- 密码使用 SHA-256 哈希比对
- 统一错误消息防止用户枚举

### 2.2 文档接口（routes_document.py）
- **GET /documents** — 列出本租户文档（需 doc.read）
- **GET /documents/\<id\>** — 获取单个文档（需 doc.read + 同租户）
- **POST /documents** — 创建文档（需 doc.write，201）
- **PUT /documents/\<id\>** — 更新文档（需 doc.write + owner 或 doc.write.any，支持部分更新）
- **DELETE /documents/\<id\>** — 删除文档（需 doc.delete + 同租户）

### 2.3 角色管理接口（routes_role.py）
- **POST /roles** — 创建角色（需 role.manage，支持父角色和权限关联，201）
- **GET /roles** — 列出本租户角色（含权限 code 数组）
- **PUT /roles/\<id\>/permissions** — 部分更新角色权限和父角色（permissions 和 parent_role_id 均可选）
- **POST /users/\<id\>/roles** — 分配角色给用户（租户隔离校验）
- **DELETE /users/\<id\>/roles/\<role_id\>** — 移除用户角色（幂等）

### 2.4 关键算法
- **权限继承遍历**：沿 parent_role_id 链递归收集权限，visited 集合防环
- **循环检测算法**：设置 parent_role_id 时从新父角色向上遍历，检测是否会形成环

## 3. 修改的文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `starter/routes_auth.py` | 新增实现 | POST /login 认证接口 |
| `starter/routes_document.py` | 新增实现 | 5 个文档 CRUD 接口 |
| `starter/routes_role.py` | 新增实现 | 5 个角色管理接口 + 循环检测 |
| `starter/app.py` | 未修改 | 按要求保持原样 |
| `starter/models.py` | 未修改 | 按要求保持原样 |
| `starter/middleware.py` | 未修改 | 按要求保持原样 |

## 4. 测试覆盖

- **测试命令**：`python -m pytest tests/test_basic.py -v`
- **测试结果**：**19/19 全部通过**（exit code 0）
- **覆盖场景**：
  - 认证（3 个）：缺失 token、无效 JWT、过期 JWT
  - 角色管理（4 个）：创建角色、权限拒绝、继承生效、循环拒绝
  - 文档 RBAC（6 个）：viewer 可读/不可写、editor 编辑自己/不可编辑他人、admin write.any、无权限
  - 多租户（3 个）：跨租户文档 404、跨租户角色禁止、文档列表租户隔离
  - 权限继承（3 个）：权限传播、权限撤销、多角色并集

## 5. 项目阶段总结

| 阶段 | ATU | 状态 | 说明 |
|------|-----|------|------|
| 需求分析 | ATU-001 | ✅ Done | 首次退回（5 个问题），修复后通过 |
| 方案设计 | ATU-002 | ✅ Done | 一次通过 |
| 开发-认证 | ATU-003 | ✅ Done | 一次通过 |
| 开发-文档 | ATU-004 | ✅ Done | 一次通过 |
| 开发-角色 | ATU-005 | ✅ Done | 一次通过 |
| 测试验证 | ATU-006 | ✅ Done | 19/19 通过 |
| 最终交付 | ATU-007 | ✅ Done | — |

## 6. 已知问题与改进建议

| # | 问题 | 严重度 | 建议 |
|---|------|--------|------|
| 1 | `datetime.utcnow()` 已在 Python 3.12 中弃用 | 低 | 迁移到 `datetime.now(datetime.timezone.utc)` |
| 2 | SQLAlchemy `Query.get()` 在 2.0 中标记为 legacy | 低 | 迁移到 `db.session.get()` |
| 3 | JWT 密钥使用默认值 'dev-secret-key' | 中 | 生产环境必须配置强密钥 |
| 4 | 密码使用 SHA-256 哈希（无加盐） | 中 | 生产环境应使用 bcrypt/argon2 |
| 5 | 会话存储为内存 SQLite | 低 | 生产环境应使用持久化数据库 |

## 7. 交付物清单

- [x] `requirements.md` — 需求分析文档
- [x] `design.md` — 方案设计文档
- [x] `starter/routes_auth.py` — 认证接口实现
- [x] `starter/routes_document.py` — 文档接口实现
- [x] `starter/routes_role.py` — 角色管理接口实现
- [x] `test-report.md` — 测试报告
- [x] `delivery-summary.md` — 交付总结
- [x] `state.json` — 项目状态追踪
