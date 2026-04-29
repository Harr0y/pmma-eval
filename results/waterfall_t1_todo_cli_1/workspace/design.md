# 方案设计文档 — T1-1：命令行待办工具 (Simple Todo CLI)

## 1. 架构概述

本项目是一个简单的命令行工具，采用单文件架构 `starter/todo.py`，通过 `sys.argv` 解析命令行参数，使用纯文本文件 `todos.txt` 持久化存储任务数据。

## 2. 数据存储设计

### 2.1 存储文件

- **文件名**：`todos.txt`（位于当前工作目录）
- **格式**：每行一条任务，行尾 `\n`
- **编码**：UTF-8（Python 默认）
- **读取**：通过已有的 `load_todos()` 函数，返回 `List[str]`（已过滤空行并 strip）
- **写入**：通过已有的 `save_todos(todos)` 函数，写入列表每行追加 `\n`

### 2.2 任务 ID 映射

任务 ID 采用 1-based 行号，即 `todos` 列表的索引 + 1：

```
todos[0] → ID 1
todos[1] → ID 2
...
todos[n-1] → ID n
```

## 3. 命令行接口设计

### 3.1 命令路由

```
sys.argv[0] = "todo.py"
sys.argv[1] = command ("add" | "list" | "remove")
sys.argv[2] = argument (任务内容 或 ID)
```

### 3.2 各命令详细设计

#### `add` 命令

```python
if command == "add":
    if len(sys.argv) < 3:
        print("Usage: python todo.py add \"任务内容\"")
        return
    todo_text = sys.argv[2]
    todos = load_todos()
    todos.append(todo_text)
    save_todos(todos)
```

**设计决策**：
- `add` 不产生标准输出（静默成功），符合测试期望
- 任务内容直接取 `sys.argv[2]`，shell 引号解析由 shell 层处理
- `load_todos()` → `append` → `save_todos()` 保证幂等性

#### `list` 命令

```python
elif command == "list":
    todos = load_todos()
    for i, todo in enumerate(todos):
        print(f"{i + 1}: {todo}")
```

**设计决策**：
- 使用 `enumerate(todos)` 生成 1-based 行号
- 没有任务时 `todos` 为空列表，`for` 循环不执行，无输出 — 满足"空输出"要求
- 输出格式 `"{i+1}: {todo}"`，与测试断言 `"1: Buy milk"` 一致

#### `remove` 命令

```python
elif command == "remove":
    if len(sys.argv) < 3:
        print("Usage: python todo.py remove <ID>")
        return
    try:
        idx = int(sys.argv[2]) - 1  # 转换为 0-based 索引
    except ValueError:
        return  # 非数字 ID，静默忽略
    todos = load_todos()
    if 0 <= idx < len(todos):
        todos.pop(idx)
        save_todos(todos)
    # ID 超出范围时静默忽略，不做任何操作
```

**设计决策**：
- 使用 `try/except ValueError` 处理非数字输入，静默忽略
- 使用 `0 <= idx < len(todos)` 边界检查，超出范围时不执行删除操作
- 删除后 `save_todos()` 重写文件，后续任务 ID 自动重新编号（1-based）
- 不产生标准输出（静默成功）

### 3.3 无参数 / 未知命令处理

```python
if len(sys.argv) < 2:
    print("Usage: python todo.py [add|list|remove] [args]")
    return
```

**设计决策**：
- 保持 starter 代码现有行为不变
- 未知命令不额外处理，等同于无操作（不影响测试）

## 4. 关键算法逻辑

### 4.1 删除后 ID 重编号

删除操作通过 `list.pop(idx)` 移除元素后，列表自动收缩。后续 `save_todos()` 写回时，文件行号自然重排。下次 `list` 时通过 `enumerate` 重新生成连续 ID。

**示例**：
```
删除前：1: A, 2: B, 3: C
删除 ID=2（索引 1）后：1: A, 2: C
```

### 4.2 边界条件处理矩阵

| 场景 | 输入 | 预期行为 |
|------|------|----------|
| 正常添加 | `add "Buy milk"` | 追加到列表末尾 |
| 特殊字符 | `add "!@#$%^&*()"` | 原样保存和显示 |
| 空列表 | `list` | 无输出 |
| 正常删除 | `remove 1` | 删除第一条任务 |
| ID 超出范围 | `remove 99` | 静默忽略 |
| ID 为 0 | `remove 0` | idx=-1，不满足 `0 <= idx`，静默忽略 |
| ID 为负数 | `remove -1` | idx=-2，不满足 `0 <= idx`，静默忽略 |
| ID 非数字 | `remove abc` | ValueError 被捕获，静默忽略 |
| 无参数 | `python todo.py` | 打印 Usage |

## 5. 实现计划

### ATU 拆分

本项目实现集中在 `starter/todo.py` 的 `main()` 函数中，作为单一 ATU-003 实现：

| 步骤 | 内容 | 涉及代码 |
|------|------|----------|
| 1 | 实现 `add` 命令逻辑 | `main()` 中 `if command == "add"` 分支 |
| 2 | 实现 `list` 命令逻辑 | `main()` 中 `elif command == "list"` 分支 |
| 3 | 实现 `remove` 命令逻辑（含边界处理） | `main()` 中 `elif command == "remove"` 分支 |

### 执行顺序

```
ATU-003（实现 main() 全部三个命令分支）
    ↓
Tester 运行测试
    ↓
Reviewer 代码审查
```

### 修改范围

- **修改文件**：`starter/todo.py`（仅 `main()` 函数）
- **不修改**：`load_todos()`、`save_todos()`、`tests/test_todo.py`
