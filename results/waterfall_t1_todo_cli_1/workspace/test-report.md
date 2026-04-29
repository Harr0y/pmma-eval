# 测试报告 — ATU-004

## 测试概要

| 项目 | 结果 |
|------|------|
| 测试文件 | `tests/test_todo.py` |
| 被测程序 | `starter/todo.py` |
| 测试用例数 | 4 |
| 通过 | 4 |
| 失败 | 0 |
| 执行耗时 | 0.17s |
| 总体结论 | ✅ 符合交付标准 |

## 执行环境

| 项目 | 信息 |
|------|------|
| 执行目录 | `workspace/` |
| Python 版本 | 3.x（系统默认） |
| 操作系统 | macOS |
| 执行命令 | `python -m pytest tests/test_todo.py -v` |

## 测试执行结果

```
tests/test_todo.py::TestBasicFlow::test_add_list_remove PASSED       [ 25%]
tests/test_todo.py::TestEdgeCases::test_list_empty PASSED            [ 50%]
tests/test_todo.py::TestEdgeCases::test_remove_nonexistent_id PASSED [ 75%]
tests/test_todo.py::TestEdgeCases::test_add_special_characters PASSED [100%]

4 passed in 0.17s
```

## 逐条验收结果

### AC-01：基本流程 — ✅ 通过

| 步骤 | 预期 | 实际（stdout / returncode） | 断言条件 | 结果 |
|------|------|---------------------------|----------|------|
| `add "Buy milk"` | returncode 0 | returncode=0, stdout="" | `r.returncode == 0` | PASS |
| `add "Clean room"` | returncode 0 | returncode=0, stdout="" | `r.returncode == 0` | PASS |
| `list` | 输出含 `1: Buy milk` 和 `2: Clean room` | stdout="1: Buy milk\n2: Clean room\n" | `"1: Buy milk" in r.stdout` and `"2: Clean room" in r.stdout` | PASS |
| `remove 1` | returncode 0 | returncode=0 | `r.returncode == 0` | PASS |
| `list`（删除后） | 输出含 `1: Clean room`，**不包含** `Buy milk` | stdout="1: Clean room\n" | `"1: Clean room" in r.stdout` and `"Buy milk" not in r.stdout` | PASS |

### AC-02：边界条件 — ✅ 通过

| 条件 | 预期 | 实际（stdout / returncode） | 断言条件 | 结果 |
|------|------|---------------------------|----------|------|
| 空 `list` | stdout.strip() == "" | stdout=""（长度为 0） | `r.stdout.strip() == ""` | PASS |
| 删除不存在的 ID (99) | 不崩溃，returncode 0 | returncode=0 | `r.returncode == 0` | PASS |
| 特殊字符 `!@#$%^&*()` | list 时正确显示 | stdout="1: Special !@#$%^&*()\n" | `"Special !@#$%^&*()" in r.stdout` | PASS |

### AC-03：测试通过 — ✅ 通过

`tests/test_todo.py` 中全部 4 个测试用例通过。

## 额外边界验证（手动验证，非自动化测试）

> **注意**：以下验证场景由 Tester 子 Agent 在开发阶段通过手动执行 `python3 starter/todo.py` 验证，未写入 `tests/test_todo.py` 自动化测试文件。结果基于 Tester 子 Agent 的执行报告，不具备自动化可重复性。

| 场景 | 验证方式 | 预期 | 结果 |
|------|----------|------|------|
| 无参数调用 | `python3 starter/todo.py` | 输出 Usage, returncode 0 | PASS |
| `remove 0` | `python3 starter/todo.py remove 0` | 静默忽略，任务不变 | PASS |
| `remove -1` | `python3 starter/todo.py remove -1` | 静默忽略，任务不变 | PASS |
| `remove abc`（非数字） | `python3 starter/todo.py remove abc` | 静默忽略，任务不变 | PASS |
| 连续多次 remove 后 list | 先 add 3 项，remove 2，再 remove 1 | ID 自动重编号 | PASS |
| `add` 缺少参数 | `python3 starter/todo.py add` | 打印 Usage, returncode 0 | PASS |
| `remove` 缺少参数 | `python3 starter/todo.py remove` | 打印 Usage, returncode 0 | PASS |
