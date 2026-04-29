# 实现说明 — ATU-003

## 修改文件

| 文件 | 修改内容 |
|------|----------|
| `starter/todo.py` | 替换 `main()` 函数中的 `pass`，实现 add、list、remove 三个命令分支 |

## 未修改文件

- `load_todos()` — 未修改
- `save_todos()` — 未修改
- `DB_FILE` — 未修改
- `tests/test_todo.py` — 未修改

## design.md 规格点实现情况

| 设计规格 | 实现状态 | 说明 |
|----------|----------|------|
| `add` 命令 - 参数验证 | ✅ | `len(sys.argv) < 3` 时打印 Usage 并 return |
| `add` 命令 - 核心逻辑 | ✅ | `sys.argv[2]` → `load_todos()` → `append` → `save_todos()` |
| `add` 命令 - 静默成功 | ✅ | 正常路径无标准输出 |
| `list` 命令 - 核心逻辑 | ✅ | `enumerate(todos)` → `print(f"{i+1}: {todo}")` |
| `list` 命令 - 空列表 | ✅ | 空列表时 for 循环不执行，无输出 |
| `remove` 命令 - 参数验证 | ✅ | `len(sys.argv) < 3` 时打印 Usage |
| `remove` 命令 - 类型转换 | ✅ | `int(sys.argv[2]) - 1` |
| `remove` 命令 - ValueError | ✅ | 非数字 ID 被 try/except 捕获 |
| `remove` 命令 - 边界检查 | ✅ | `0 <= idx < len(todos)` |
| 无参数处理 | ✅ | 保持 starter 代码现有行为 |

## 已知限制

无。实现严格遵循 design.md，未引入任何偏离设计的逻辑。
