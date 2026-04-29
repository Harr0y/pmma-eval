# 需求分析文档 — T1-1：命令行待办工具 (Simple Todo CLI)

## 1. 概述

开发一个简单的命令行待办事项工具 `todo.py`，支持添加、列出和删除任务，使用纯文本文件 `todos.txt` 作为持久化存储。

## 2. 功能需求

### FR-01：添加任务 (`add`)

- **命令格式**：`python todo.py add "任务内容"`
- **行为**：将任务内容追加到 `todos.txt` 文件末尾
- **输入约束**：
  - 任务内容可能包含特殊字符（如 `!@#$%^&*()`），必须原样保存和显示，不得转义或丢失
  - 任务内容通过 shell 命令行参数传入，受 shell 引号规则约束（如双引号内的双引号需转义）。程序本身不需要处理 shell 层面的引号问题
- **输出**：无标准输出（静默成功）
- **返回值**：returncode == 0（`main()` 函数正常执行完毕后进程退出码应为 0，这是 Python 默认行为）

### FR-02：列出任务 (`list`)

- **命令格式**：`python todo.py list`
- **行为**：读取 `todos.txt`，逐行显示任务，格式为 `ID: 内容`
- **输出格式**：
  - 每行格式：`{行号}: {任务内容}`（行号从 1 开始）
  - 没有任务时：**不应输出任何内容**（空输出，stdout 为空字符串）
- **返回值**：returncode == 0

### FR-03：删除任务 (`remove`)

- **命令格式**：`python todo.py remove <ID>`
- **行为**：根据行号删除指定任务
- **输入约束**：
  - `<ID>` 为正整数（对应 1-based 行号）
- **边界条件**：
  - 如果 ID 不存在（超出范围或无效），**不应崩溃**，静默忽略即可
  - ID 为 0 或负数时，同样静默忽略
- **返回值**：returncode == 0

### FR-04：无参数调用

- **命令格式**：`python todo.py`（无子命令）
- **行为**：打印 Usage 信息
- **输出**：`Usage: python todo.py [add|list|remove] [args]`
- **返回值**：returncode == 0
- **说明**：此行为继承自 starter 代码的现有实现，非 README 新增需求

## 3. 数据模型需求

### DM-01：存储格式

- **文件名**：`todos.txt`
- **格式**：每行一条任务，行尾 `\n`
- **任务 ID**：行号（1-based），由文件中的物理行位置决定
- **空行处理**：`load_todos()` 读取时自动过滤空行（通过 `if line.strip()` 条件），因此空行不会进入内存列表，`save_todos()` 写回时自然不含空行。程序运行过程中不会产生空行

### DM-02：现有基础设施

- `load_todos()` 函数已实现：读取文件，返回非空行列表（已 strip）
- `save_todos()` 函数已实现：写入列表，每行追加 `\n`
- **约束**：不得修改 `load_todos()` 和 `save_todos()` 的现有实现

## 4. 接口行为描述

### 4.1 添加任务流程

```
用户输入 → sys.argv 解析 → 验证参数数量 → load_todos() → append 任务 → save_todos()
```

### 4.2 列出任务流程

```
用户输入 → sys.argv 解析 → load_todos() → 遍历列表 → print(f"{i+1}: {todo}")
```

### 4.3 删除任务流程

```
用户输入 → sys.argv 解析 → 验证 ID 范围 → load_todos() → 删除指定索引 → save_todos()
```

## 5. 验收标准

### AC-01：基本流程
- `python todo.py add "Buy milk"` → 成功（returncode 0）
- `python todo.py add "Clean room"` → 成功
- `python todo.py list` → 输出包含 `1: Buy milk` 和 `2: Clean room`
- `python todo.py remove 1` → 成功
- `python todo.py list` → 输出包含 `1: Clean room`，不包含 `Buy milk`

### AC-02：边界条件
- 空列表 `list` → stdout 为空（`stdout.strip() == ""`）
- 删除不存在的 ID（如 99）→ 不崩溃，returncode 0
- 添加含特殊字符的任务 `!@#$%^&*()` → `list` 时正确显示

### AC-03：测试通过
- 在 `workspace/` 目录下执行 `python -m pytest tests/test_todo.py`
- `tests/test_todo.py` 中全部 4 个测试用例通过
