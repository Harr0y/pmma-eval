# ATU-003 实现说明

## 修改的文件

- `starter/todo.py` — 仅修改了 `main()` 函数（将 `pass` 替换为实际实现）

## 设计规格点逐条实现情况

| 设计规格点 | design.md 章节 | 实现状态 | 说明 |
|---|---|---|---|
| 命令路由 | 2.1 | ✅ 已实现 | 根据 `sys.argv[1]` 分支为 `add`/`list`/`remove` |
| add: 参数提取 | 2.2 | ✅ 已实现 | `sys.argv[2]` 作为任务内容 |
| add: 追加到列表末尾 | 2.2 | ✅ 已实现 | `todos.append(sys.argv[2])` |
| add: 调用 save_todos 写回 | 2.2 | ✅ 已实现 | `save_todos(todos)` |
| add: 特殊字符处理 | 2.2 | ✅ 已实现 | Python 字符串天然支持，无需额外处理 |
| add: 缺少参数处理 | 2.2 (边界) | ✅ 已实现（返工） | `len(sys.argv) < 3` 检查，打印用法并正常返回 |
| list: 空列表不输出 | 2.3 | ✅ 已实现 | 空列表时 `for` 循环不执行，自然无输出 |
| list: 格式 `{i+1}: {todo}` | 2.3 | ✅ 已实现 | `print(f"{i + 1}: {todo}")` |
| remove: 参数转整数 | 2.4 | ✅ 已实现 | `todo_id = int(sys.argv[2])` |
| remove: 非整数输入处理 | 2.4 (边界) | ✅ 已实现（返工） | `try-except ValueError` 捕获非整数输入，静默返回 |
| remove: 缺少参数处理 | 2.4 (边界) | ✅ 已实现（返工） | `len(sys.argv) < 3` 检查，打印用法并正常返回 |
| remove: 范围检查 `1 <= id <= len(todos)` | 2.4 | ✅ 已实现 | `if 1 <= todo_id <= len(todos):` |
| remove: 范围内 pop(id-1) 并写回 | 2.4 | ✅ 已实现 | `todos.pop(todo_id - 1)` + `save_todos(todos)` |
| remove: 越界静默忽略 | 2.4 | ✅ 已实现 | 超出范围时不执行任何操作 |
| ID 重排 | 3.2 | ✅ 已实现 | ID 是运行时根据行号动态计算的，删除后自动重排 |
| 变量命名 | 代码质量 | ✅ 已修复（返工） | `id` 重命名为 `todo_id`，避免遮蔽内置函数 |

## 返工记录

### 第 1 轮返工（Reviewer 审查退回）

| # | 优先级 | 问题 | 修复 |
|---|--------|------|------|
| 1 | P0 | `remove abc` 导致 ValueError 崩溃 | 添加 `try-except ValueError` 静默返回 |
| 2 | P1 | `add` 缺少参数时 IndexError 崩溃 | `len(sys.argv) < 3` 检查，打印用法并返回 |
| 3 | P1 | `remove` 缺少参数时 IndexError 崩溃 | 同上 |
| 4 | P2 | 变量名 `id` 遮蔽内置函数 | 重命名为 `todo_id` |

## 关键约束遵守情况

- `load_todos()` 和 `save_todos()` 函数：**未修改**
- 测试文件 `tests/test_todo.py`：**未修改**
- 仅修改了 `main()` 函数中的 `pass`：**是**

## 已知限制

- 空字符串任务场景：因 `load_todos()` 骨架代码中 `line.strip()` 过滤逻辑，添加空字符串任务后无法正确加载。此为骨架代码限制，不在本次修改范围内。
