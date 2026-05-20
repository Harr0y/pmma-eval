import subprocess
import os

def run_todo(*args):
    """Helper to run todo.py and return CompletedProcess."""
    return subprocess.run(
        ["python3", "starter/todo.py", *args],
        capture_output=True, text=True
    )

def cleanup():
    if os.path.exists("todos.txt"):
        os.remove("todos.txt")


class TestBasicFlow:
    def test_add_list_remove(self):
        """基本流程：添加 → 列表 → 删除 → 确认"""
        cleanup()
        # Add
        r = run_todo("add", "Buy milk")
        assert r.returncode == 0, f"add failed: {r.stderr}"
        r = run_todo("add", "Clean room")
        assert r.returncode == 0, f"add failed: {r.stderr}"

        # List
        r = run_todo("list")
        assert r.returncode == 0
        assert "1: Buy milk" in r.stdout
        assert "2: Clean room" in r.stdout

        # Remove
        r = run_todo("remove", "1")
        assert r.returncode == 0, f"remove failed: {r.stderr}"

        # Verify
        r = run_todo("list")
        assert "1: Clean room" in r.stdout
        assert "Buy milk" not in r.stdout
        cleanup()


class TestEdgeCases:
    def test_list_empty(self):
        """空列表应无输出"""
        cleanup()
        r = run_todo("list")
        assert r.returncode == 0
        assert r.stdout.strip() == "", f"Expected empty output, got: {r.stdout!r}"
        cleanup()

    def test_remove_nonexistent_id(self):
        """删除不存在的 ID 不应崩溃"""
        cleanup()
        r = run_todo("remove", "99")
        assert r.returncode == 0, f"remove 99 crashed: {r.stderr}"
        cleanup()

    def test_add_special_characters(self):
        """任务内容包含特殊字符应正确处理"""
        cleanup()
        r = run_todo("add", "Special !@#$%^&*()")
        assert r.returncode == 0, f"add special chars failed: {r.stderr}"
        r = run_todo("list")
        assert "Special !@#$%^&*()" in r.stdout
        cleanup()
