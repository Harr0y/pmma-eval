# 需求分析文档

## 1. 项目概述

开发一个简单的命令行待办事项工具 `todo.py`，支持添加、列出和删除任务。数据使用文本文件存储。

## 2. 功能需求

### FR-1：添加任务 (`add`)
- **命令格式**：`python todo.py add "任务内容"`
- **行为**：将任务内容追加到存储文件末尾
- **约束**：
  - 任务内容可能包含特殊字符（如 `!@#$%^&*()`），必须正确保存和显示
  - 命令执行成功返回码为 0

### FR-2：列出任务 (`list`)
- **命令格式**：`python todo.py list`
- **行为**：显示所有任务，格式为 `ID: 内容`，ID 为 1-based 行号
- **约束**：
  - 没有任务时不应输出任何内容（空输出，stdout 为空字符串）
  - 命令执行成功返回码为 0

### FR-3：删除任务 (`remove`)
- **命令格式**：`python todo.py remove <ID>`
- **行为**：根据 1-based ID 删除对应任务，后续任务 ID 重新编号
- **约束**：
  - 如果 ID 不存在（超出范围或无效），不应崩溃，静默忽略
  - 命令执行成功返回码为 0（即使删除的是不存在的 ID）

## 3. 数据模型

- **存储介质**：纯文本文件 `todos.txt`（与 todo.py 同目录）
- **格式**：每行一个任务，行尾为换行符 `\n`
- **任务 ID**：由行号决定，从 1 开始（1-based）
- **空行处理**：不应存储空行

## 4. 非功能需求

- **进程模型**：命令行单次执行，无持久化进程
- **错误处理**：所有错误情况均静默处理，不崩溃，不输出错误信息到 stderr
- **输出规范**：正常操作输出到 stdout，错误情况下 stderr 应为空

## 5. 验收标准

| 编号 | 验收条件 | 对应测试 |
|------|----------|----------|
| AC-1 | `python todo.py add "Buy milk"` 成功添加任务 | `test_add_list_remove` |
| AC-2 | `python todo.py list` 正确显示 `1: Buy milk` | `test_add_list_remove` |
| AC-3 | 添加多个任务后 list 按顺序显示 | `test_add_list_remove` |
| AC-4 | `python todo.py remove 1` 成功删除任务 | `test_add_list_remove` |
| AC-5 | 删除后 list 中 ID 重新编号 | `test_add_list_remove` |
| AC-6 | 无任务时 list 输出为空 | `test_list_empty` |
| AC-7 | 删除不存在的 ID 不崩溃 | `test_remove_nonexistent_id` |
| AC-8 | 特殊字符（`!@#$%^&*()`）正确保存和显示 | `test_add_special_characters` |

## 6. 已有基础设施

- `starter/todo.py`：已提供骨架代码，包含 `load_todos()` 和 `save_todos()` 函数
- `tests/test_todo.py`：已提供 4 个测试用例覆盖基本流程和边界条件
- 测试通过 `subprocess.run` 调用 `starter/todo.py`，工作目录为项目根目录
