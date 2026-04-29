# 设计规格说明 — T1-1 命令行待办工具 (Simple Todo CLI)

## 1. 总体架构

单文件 Python CLI 应用，`main()` 函数为入口，通过 `sys.argv` 解析命令，分派到对应的处理逻辑。

```
main() → 命令解析 → {add | list | remove}
                          ↓
                    load_todos() / save_todos()
                          ↓
                      todos.txt
```

## 2. 数据模型

### 2.1 存储格式

`todos.txt` 为纯文本文件，每行一个任务内容（不含 ID）：

```
Buy milk
Clean room
Special !@#$%^&*()
```

### 2.2 ID 映射

ID = 行号（1-based），通过列表索引 +1 得到。不显式存储 ID。

### 2.3 内存表示

使用 Python `list[str]` 表示所有任务，每个元素为一行任务内容。

## 3. 命令设计

### 3.1 命令解析

```python
def main():
    if len(sys.argv) < 2:
        print("Usage: python todo.py [add|list|remove] [args]")
        return

    command = sys.argv[1]

    if command == "add":
        # sys.argv[2] 为任务内容
        ...
    elif command == "list":
        ...
    elif command == "remove":
        # sys.argv[2] 为任务 ID（字符串形式）
        ...
```

### 3.2 `add` 命令

**规格点 ADD-1**：读取现有任务列表 → 追加新任务 → 写回文件

```python
todos = load_todos()
todos.append(task_content)
save_todos(todos)
```

**边界条件**：
- 无边界问题：任何字符串均可追加
- `load_todos()` 在文件不存在时返回空列表，首次 `add` 自动处理

### 3.3 `list` 命令

**规格点 LIST-1**：读取任务列表 → 逐行输出 `ID: 内容`

```python
todos = load_todos()
for i, todo in enumerate(todos):
    print(f"{i + 1}: {todo}")
```

**边界条件**（规避 Reviewer 提出的 FR-2 措辞问题）：
- 空列表时 `enumerate(todos)` 不产生任何迭代，`print()` 不被调用 → stdout 为空字符串
- 这同时满足"stdout 为空字符串"和 `r.stdout.strip() == ""` 的测试断言

### 3.4 `remove` 命令

**规格点 REMOVE-1**：解析 ID → 范围校验 → 删除 → 写回文件

```python
todos = load_todos()
try:
    index = int(sys.argv[2]) - 1  # 转为 0-based
except (ValueError, IndexError):
    return  # 静默忽略

if 0 <= index < len(todos):
    todos.pop(index)
    save_todos(todos)
# else: 静默忽略不存在的 ID
```

**边界条件**：
- ID 为非数字字符串（如 `abc`）→ `ValueError` 被捕获，静默返回
- ID 为 0 或负数 → `index < 0`，不在 `0 <= index < len(todos)` 范围内，静默忽略
- ID 超出范围（如 99）→ `index >= len(todos)`，静默忽略
- 空列表时 remove → `len(todos) == 0`，任何 ID 都不在范围内，静默忽略

## 4. 复用已有函数

| 函数 | 复用方式 |
|------|----------|
| `load_todos()` | 所有命令均调用，读取任务列表 |
| `save_todos(todos)` | `add` 和 `remove` 命令调用，写回任务列表 |

**注意**：不修改 `load_todos()` 和 `save_todos()` 的实现，仅在 `main()` 中调用。

## 5. 实现计划

### ATU 拆分

本项目仅一个实现 ATU（ATU-003），一次性完成所有命令逻辑：

| ATU | 内容 | 文件 | 复杂度 |
|-----|------|------|--------|
| ATU-003 | 实现 `main()` 中的 `add`、`list`、`remove` 三个命令分支 | `starter/todo.py` | S |

### 执行顺序

1. 实现 `add` 命令分支
2. 实现 `list` 命令分支
3. 实现 `remove` 命令分支（含边界条件处理）
4. 移除 `pass` 占位符

### 修改范围

仅修改 `starter/todo.py` 的 `main()` 函数体（第 18-30 行），替换 `pass` 为实际逻辑。不修改文件其他部分。

## 6. 测试覆盖映射

| 测试用例 | 覆盖的验收标准 | 覆盖的规格点 |
|----------|---------------|-------------|
| `test_add_list_remove` | AC-1, AC-2 | ADD-1, LIST-1, REMOVE-1 |
| `test_list_empty` | AC-3 | LIST-1（空列表边界） |
| `test_remove_nonexistent_id` | AC-4 | REMOVE-1（越界边界） |
| `test_add_special_characters` | AC-5 | ADD-1（特殊字符边界） |
