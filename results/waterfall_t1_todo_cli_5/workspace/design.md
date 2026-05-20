# 方案设计文档 — T1-1 命令行待办工具 (Simple Todo CLI)

## 1. 设计概述

本设计基于 `requirements.md` 中的需求规格，在已有的 `starter/todo.py` 框架代码基础上实现 `add`、`list`、`remove` 三个命令。

## 2. 数据存储设计

### 2.1 文件格式

- **文件**: `todos.txt`（相对路径，位于进程工作目录）
- **格式**: 纯文本，每行一个任务，无额外空行
- **读写**: 复用已有的 `load_todos()` 和 `save_todos()` 函数

### 2.2 数据流

```
用户命令 → sys.argv 解析 → load_todos() 读取 → 内存操作 → save_todos() 写回
```

所有操作均在内存中完成，最终通过 `save_todos()` 原子写入文件。这保证了：
- 操作的一致性（读-改-写是原子的）
- 删除操作自动重新编号（因为 ID 基于列表索引）

## 3. CLI 命令解析设计

### 3.1 参数解析

```
sys.argv[0] = "starter/todo.py"（或 "todo.py"）
sys.argv[1] = 命令 ("add" | "list" | "remove")
sys.argv[2] = 参数（任务内容 for add, ID for remove）
```

### 3.2 命令分发逻辑（main() 函数内）

```python
def main():
    if len(sys.argv) < 2:
        print("Usage: python todo.py [add|list|remove] [args]")
        return

    command = sys.argv[1]

    if command == "add":
        # 3.3.1 add 命令实现
    elif command == "list":
        # 3.3.2 list 命令实现
    elif command == "remove":
        # 3.3.3 remove 命令实现
```

## 4. 各命令详细设计

### 4.1 `add` 命令

**设计规格 ADD-1: 添加任务**

```python
if command == "add":
    if len(sys.argv) < 3:
        return  # 缺少参数，静默忽略
    content = sys.argv[2]
    todos = load_todos()
    todos.append(content)
    save_todos(todos)
```

**规格点**:
- ADD-1.1: 从 `sys.argv[2]` 获取任务内容
- ADD-1.2: 使用 `load_todos()` 读取当前列表
- ADD-1.3: 将任务内容 `append` 到列表末尾
- ADD-1.4: 使用 `save_todos()` 写回文件
- ADD-1.5: 参数不足时（`len(sys.argv) < 3`）静默 return，不崩溃
- ADD-1.6: 任务内容不做任何处理（原样保存特殊字符）

### 4.2 `list` 命令

**设计规格 LIST-1: 列出任务**

```python
elif command == "list":
    todos = load_todos()
    for idx, todo in enumerate(todos, start=1):
        print(f"{idx}: {todo}")
```

**规格点**:
- LIST-1.1: 使用 `load_todos()` 读取当前列表
- LIST-1.2: 使用 `enumerate(todos, start=1)` 生成 1-based ID
- LIST-1.3: 格式为 `f"{idx}: {todo}"`（ID、冒号、空格、内容）
- LIST-1.4: 列表为空时不输出任何内容（for 循环不执行）
- LIST-1.5: 文件不存在时 `load_todos()` 返回空列表，同样无输出

### 4.3 `remove` 命令

**设计规格 REMOVE-1: 删除任务**

```python
elif command == "remove":
    if len(sys.argv) < 3:
        return  # 缺少参数，静默忽略
    try:
        idx = int(sys.argv[2]) - 1  # 转换为 0-based 索引
    except (ValueError, IndexError):
        return  # 非整数参数，静默忽略
    todos = load_todos()
    if 0 <= idx < len(todos):
        todos.pop(idx)
        save_todos(todos)
    # idx 超出范围时不做任何操作，静默忽略
```

**规格点**:
- REMOVE-1.1: 从 `sys.argv[2]` 获取 ID 字符串
- REMOVE-1.2: 参数不足时（`len(sys.argv) < 3`）静默 return
- REMOVE-1.3: 将 ID 转换为整数并减 1 得到 0-based 索引
- REMOVE-1.4: 转换失败（非整数）时静默 return，不崩溃
- REMOVE-1.5: 索引越界（`idx < 0` 或 `idx >= len(todos)`）时静默忽略
- REMOVE-1.6: 索引有效时，使用 `pop(idx)` 删除并 `save_todos()` 写回
- REMOVE-1.7: 删除后列表自动重新编号（因为 ID 基于列表索引，无需额外操作）

## 5. 边界条件处理汇总

| 场景 | 处理方式 | 退出码 |
|------|----------|--------|
| 无命令参数 | 打印 Usage，return | 0 |
| `add` 缺少内容 | 静默 return | 0 |
| `remove` 缺少 ID | 静默 return | 0 |
| `remove` ID 非整数 | `try/except ValueError`，静默 return | 0 |
| `remove` ID 超出范围 | `if 0 <= idx < len(todos)` 检查，跳过 | 0 |
| `list` 空列表 | `for` 循环不执行，无输出 | 0 |
| 特殊字符 | 原样传递，不做处理 | 0 |
| `todos.txt` 不存在 | `load_todos()` 返回 `[]` | 0 |

## 6. 实现计划

### ATU 拆分

| ATU ID | 内容 | 文件 | 依赖 |
|--------|------|------|------|
| ATU-003 | 实现 `main()` 中的 add/list/remove 逻辑 | `starter/todo.py` | ATU-002 |

由于本项目规模为 S（≤30 行代码，1 个文件），所有实现集中在单个 ATU-003 中完成。

### 执行顺序

1. 在 `main()` 函数中实现命令分发（if/elif 结构）
2. 实现 `add` 命令逻辑（ADD-1.1 ~ ADD-1.6）
3. 实现 `list` 命令逻辑（LIST-1.1 ~ LIST-1.5）
4. 实现 `remove` 命令逻辑（REMOVE-1.1 ~ REMOVE-1.7）
5. 移除 `main()` 末尾的 `pass` 占位语句
