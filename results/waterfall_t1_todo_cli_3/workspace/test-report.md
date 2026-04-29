# 测试报告 — T1-1 命令行待办工具 (Simple Todo CLI)

## 1. 测试环境

| 属性 | 值 |
|------|-----|
| Python 版本 | 3.14.3 |
| pytest 版本 | 9.0.3 |
| 测试日期 | 2026-04-26 |
| 测试阶段 | Waterfall 阶段 4 — 测试验证 |

## 2. 自动化测试结果

```
tests/test_todo.py::TestBasicFlow::test_add_list_remove PASSED           [ 25%]
tests/test_todo.py::TestEdgeCases::test_list_empty PASSED                [ 50%]
tests/test_todo.py::TestEdgeCases::test_remove_nonexistent_id PASSED     [ 75%]
tests/test_todo.py::TestEdgeCases::test_add_special_characters PASSED    [100%]

4 passed in 0.17s
```

**结果：4/4 全部通过 ✅**

## 3. 验收标准逐条对照

| 编号 | 验收项 | 结果 | 验证方式 |
|------|--------|------|----------|
| AC-1 | 添加任务后可通过 list 查看 | **PASS** ✅ | test_add_list_remove |
| AC-2 | 删除任务后列表正确更新（ID 重编号） | **PASS** ✅ | test_add_list_remove |
| AC-3 | 空列表时 list 无输出 | **PASS** ✅ | test_list_empty |
| AC-4 | 删除不存在的 ID 不崩溃 | **PASS** ✅ | test_remove_nonexistent_id |
| AC-5 | 特殊字符正确保存和显示 | **PASS** ✅ | test_add_special_characters |
| AC-6 | 所有测试通过 | **PASS** ✅ | 4/4 PASSED |

## 4. 非功能需求验证

| 编号 | 需求 | 结果 |
|------|------|------|
| NFR-1 | 代码仅放置于 starter/todo.py | **PASS** ✅ |
| NFR-2 | 不引入外部依赖 | **PASS** ✅（仅 sys, os） |
| NFR-3 | 复用 load_todos() 和 save_todos() | **PASS** ✅ |

## 5. 额外边界测试

| 测试项 | 结果 | 说明 |
|--------|------|------|
| 非数字 ID (remove "abc") | PASS | ValueError 被捕获，静默忽略 |
| 负数 ID (remove "-1") | PASS | 不在 0-based 范围内，静默忽略 |
| 零 ID (remove "0") | PASS | int("0")-1=-1，范围校验排除 |
| 空列表 remove | PASS | len(todos)==0，任何 ID 被排除 |
| 无命令参数 | PASS | 输出 Usage，返回码 0 |
| 未知命令 | PASS | 输出 Usage，返回码 0 |
| Unicode/中文任务 | PASS | 原样保存和显示 |

## 6. 已知限制

| 项目 | 说明 | 严重性 |
|------|------|--------|
| 空字符串任务 | add "" 后 list 不显示（load_todos 的 strip 过滤） | 信息性，需求未定义此行为 |
| 换行符注入 | 通过 subprocess 传入含 \n 的内容可能被拆行 | 低风险，shell 传递参数场景不涉及 |

## 7. 总体评估

**符合交付标准 ✅**

所有 6 项验收标准（AC-1 到 AC-6）全部通过，3 项非功能需求全部满足，额外边界测试未发现 AC 级别缺陷。
