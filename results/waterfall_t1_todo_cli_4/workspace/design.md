# 方案设计文档

## 1. 数据存储设计

### 1.1 存储文件

- **文件路径**: `todos.txt`（与 todo.py 同级目录）
- **格式**: 纯文本，每行一个任务
- **编码**: UTF-8
- **行结束符**: `\n`（Unix 风格）

### 1.2 数据结构

```
任务1内容\n
任务2内容\n
任务3内容\n
```

- 任务 ID = 行号（1-based），不存储在文件中，通过读取时的行索引计算
- 文件不存在等同于空列表

### 1.3 文件操作函数（已有骨架）

| 函数 | 职责 |
|------|------|
| `load_todos()` | 读取 todos.txt，返回非空行列表；文件不存在返回空列表 |
| `save_todos(todos)` | 将列表逐行写入 todos.txt |

## 2. 命令接口设计

### 2.1 命令路由

在 `main()` 函数中根据 `sys.argv[1]` 进行分支：

```
sys.argv[1] == "add"    → handle_add()
sys.argv[1] == "list"   → handle_list()
sys.argv[1] == "remove" → handle_remove()
```

### 2.2 `add` 命令

- **参数提取**: `sys.argv[2]` 为任务内容
- **逻辑**:
  1. 调用 `load_todos()` 获取当前列表
  2. 将 `sys.argv[2]` 追加到列表末尾
  3. 调用 `save_todos(todos)` 写回文件
- **特殊字符**: Python 字符串天然支持特殊字符，无需额外转义处理
- **退出码**: 0（正常退出）

### 2.3 `list` 命令

- **逻辑**:
  1. 调用 `load_todos()` 获取当前列表
  2. 如果列表为空，不输出任何内容，直接返回
  3. 遍历列表，格式化输出 `{i+1}: {todo}`（i 为 0-based 索引）
- **输出到 stdout**: 使用 `print()`
- **退出码**: 0

### 2.4 `remove` 命令

- **参数提取**: `sys.argv[2]` 为要删除的 ID 字符串
- **逻辑**:
  1. 调用 `load_todos()` 获取当前列表
  2. 将 `sys.argv[2]` 转为整数 `id`
  3. 检查 `1 <= id <= len(todos)`：
     - **在范围内**: `todos.pop(id - 1)`，调用 `save_todos(todos)` 写回
     - **超出范围**: 静默忽略，不做任何操作
  4. 注意：负数情况也包含在越界检查中（`id < 1` 时直接忽略）
- **退出码**: 0（无论成功删除还是越界）

## 3. 关键算法逻辑

### 3.1 add 流程

```
load_todos() → append content → save_todos()
```

无需去重或验证，直接追加。

### 3.2 remove 流程

```
load_todos() → validate id range → pop(index) → save_todos()
```

关键：删除后无需手动更新 ID，因为 ID 是运行时根据行号动态计算的。

### 3.3 list 流程

```
load_todos() → enumerate with 1-based index → print each
```

关键：空列表时 `for` 循环不执行，自然实现无输出。

## 4. 实现计划

### ATU 拆分

本项目的实现包含在一个 ATU（ATU-003）中，因为：

- 总代码量 ≤ 30 行（S 级复杂度）
- 仅修改 1 个文件（`starter/todo.py`）
- 所有逻辑紧密耦合，不适合拆分

### 实现步骤

1. 在 `main()` 函数中实现 `add` 分支
2. 在 `main()` 函数中实现 `list` 分支
3. 在 `main()` 函数中实现 `remove` 分支
4. 确保所有边界条件（空列表、越界 ID、特殊字符）被覆盖

### 关键实现约束

- **不得修改** `load_todos()` 和 `save_todos()` 函数（已有正确实现）
- **不得修改** 测试文件 `tests/test_todo.py`
- 实现必须与已有骨架代码兼容（`DB_FILE`、`load_todos()`、`save_todos()`）
