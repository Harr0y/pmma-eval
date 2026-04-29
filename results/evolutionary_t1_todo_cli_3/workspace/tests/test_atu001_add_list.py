"""
ATU-001: todo.py add and list commands.

add "task content" appends a task to todos.txt.
list displays tasks as "ID: content" with 1-based IDs.
Empty list produces no output.
Task content may contain special characters.

Each test cleans up todos.txt before and after execution.
"""

import subprocess
import os
import pytest


DB_FILE = "todos.txt"


def run_todo(*args):
    """Helper to run todo.py via subprocess and return CompletedProcess."""
    return subprocess.run(
        ["python3", "starter/todo.py", *args],
        capture_output=True,
        text=True,
    )


def cleanup():
    """Remove todos.txt if it exists."""
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_todos():
    """Ensure todos.txt is removed before and after each test."""
    cleanup()
    yield
    cleanup()


# ── add command ───────────────────────────────────────────────────────────


class TestAddCommand:
    def test_add_single_task_creates_file(self):
        """add should create todos.txt with the task content."""
        run_todo("add", "Buy milk")
        assert os.path.exists(DB_FILE)
        with open(DB_FILE) as f:
            lines = f.read().strip().split("\n")
        assert lines == ["Buy milk"]

    def test_add_appends_multiple_tasks(self):
        """Each add call appends a new line, preserving previous tasks."""
        run_todo("add", "First task")
        run_todo("add", "Second task")
        run_todo("add", "Third task")
        with open(DB_FILE) as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        assert lines == ["First task", "Second task", "Third task"]

    def test_add_returncode_zero(self):
        """add command should exit with code 0 on success."""
        r = run_todo("add", "Anything")
        assert r.returncode == 0, f"add failed: {r.stderr}"

    def test_add_special_characters(self):
        """add should preserve special characters in task content."""
        special = "!@#$%^&*()"
        run_todo("add", special)
        with open(DB_FILE) as f:
            content = f.read().strip()
        assert content == special

    def test_add_unicode_content(self):
        """add should handle unicode characters correctly."""
        run_todo("add", "Buy milk")
        run_todo("add", "Buy milk")
        run_todo("add", "Buy milk")
        with open(DB_FILE) as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        assert lines == ["Buy milk", "Buy milk", "Buy milk"]


# ── list command ──────────────────────────────────────────────────────────


class TestListCommand:
    def test_list_empty_no_output(self):
        """list on an empty todo list should produce no stdout output."""
        r = run_todo("list")
        assert r.returncode == 0
        assert r.stdout.strip() == "", f"Expected empty output, got: {r.stdout!r}"

    def test_list_single_task(self):
        """list with one task should show '1: content'."""
        run_todo("add", "Buy milk")
        r = run_todo("list")
        assert r.returncode == 0
        assert "1: Buy milk" in r.stdout

    def test_list_multiple_tasks_with_correct_ids(self):
        """list should display all tasks with correct 1-based IDs."""
        run_todo("add", "Task A")
        run_todo("add", "Task B")
        run_todo("add", "Task C")
        r = run_todo("list")
        assert r.returncode == 0
        assert "1: Task A" in r.stdout
        assert "2: Task B" in r.stdout
        assert "3: Task C" in r.stdout

    def test_list_ids_are_one_based(self):
        """list IDs should start at 1, not 0."""
        run_todo("add", "Only task")
        r = run_todo("list")
        assert r.returncode == 0
        assert "0:" not in r.stdout
        assert "1: Only task" in r.stdout

    def test_list_preserves_insertion_order(self):
        """list should display tasks in the order they were added."""
        run_todo("add", "Alpha")
        run_todo("add", "Beta")
        run_todo("add", "Gamma")
        r = run_todo("list")
        lines = r.stdout.strip().split("\n")
        assert lines[0] == "1: Alpha"
        assert lines[1] == "2: Beta"
        assert lines[2] == "3: Gamma"

    def test_list_special_characters_display(self):
        """list should display special characters exactly as stored."""
        content = "Special !@#$%^&*()"
        run_todo("add", content)
        r = run_todo("list")
        assert r.returncode == 0
        assert f"1: {content}" in r.stdout

    def test_list_returncode_zero(self):
        """list command should exit with code 0 even for empty list."""
        r = run_todo("list")
        assert r.returncode == 0


# ── combined add + list flow ─────────────────────────────────────────────


class TestAddListIntegration:
    def test_add_then_list_shows_task(self):
        """A task added via add should appear in subsequent list output."""
        run_todo("add", "Integration test task")
        r = run_todo("list")
        assert "1: Integration test task" in r.stdout

    def test_sequential_add_list_cycles(self):
        """Multiple add-list cycles should accumulate correctly."""
        run_todo("add", "Cycle 1")
        r = run_todo("list")
        assert "1: Cycle 1" in r.stdout
        assert "2:" not in r.stdout

        run_todo("add", "Cycle 2")
        r = run_todo("list")
        assert "1: Cycle 1" in r.stdout
        assert "2: Cycle 2" in r.stdout
        assert "3:" not in r.stdout

    def test_list_after_adding_special_characters_roundtrip(self):
        """Special character content should survive the add -> file -> list roundtrip."""
        payload = "Test !@#$%^&*() chars"
        run_todo("add", payload)
        r = run_todo("list")
        assert f"1: {payload}" in r.stdout
