"""Tests for ATU-001: Add and List commands in todo.py.

ATU-001 scope:
- add "content" appends a task to todos.txt
- list displays all tasks as "ID: content" (1-based line number)
- Empty list produces no output
- Task content may contain special characters
- add command returns exit code 0
"""

import subprocess
import os

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODO_FILE = os.path.join(WORKSPACE, "todos.txt")
TODO_SCRIPT = os.path.join(WORKSPACE, "starter", "todo.py")


def run_todo(*args):
    """Run todo.py as a subprocess and return CompletedProcess."""
    return subprocess.run(
        ["python3", TODO_SCRIPT, *args],
        capture_output=True,
        text=True,
        cwd=WORKSPACE,
    )


def cleanup():
    """Remove todos.txt if it exists."""
    if os.path.exists(TODO_FILE):
        os.remove(TODO_FILE)


class TestAddThenList:
    """add a single task, then list verifies correct display."""

    def test_add_one_task_shows_in_list(self):
        cleanup()
        try:
            r = run_todo("add", "Buy milk")
            assert r.returncode == 0, f"add failed: {r.stderr}"

            r = run_todo("list")
            assert r.returncode == 0
            assert "1: Buy milk" in r.stdout, f"Expected '1: Buy milk' in output, got: {r.stdout!r}"
        finally:
            cleanup()

    def test_add_command_returns_zero(self):
        """add command must return exit code 0."""
        cleanup()
        try:
            r = run_todo("add", "Any task")
            assert r.returncode == 0, f"add should return 0, got {r.returncode}: {r.stderr}"
        finally:
            cleanup()


class TestMultipleTasks:
    """add multiple tasks, list shows correct order and 1-based IDs."""

    def test_order_and_ids(self):
        cleanup()
        try:
            run_todo("add", "First task")
            run_todo("add", "Second task")
            run_todo("add", "Third task")

            r = run_todo("list")
            assert r.returncode == 0
            lines = r.stdout.strip().split("\n")
            assert lines == [
                "1: First task",
                "2: Second task",
                "3: Third task",
            ], f"Unexpected list output: {lines!r}"
        finally:
            cleanup()


class TestListEmpty:
    """list on an empty todo list produces no output."""

    def test_no_output_for_empty_list(self):
        cleanup()
        try:
            r = run_todo("list")
            assert r.returncode == 0
            assert r.stdout.strip() == "", f"Expected empty output, got: {r.stdout!r}"
        finally:
            cleanup()


class TestSpecialCharacters:
    """add a task with special characters, list displays it correctly."""

    def test_special_characters_in_task(self):
        cleanup()
        try:
            special = 'Special !@#$%^&*()'
            r = run_todo("add", special)
            assert r.returncode == 0, f"add special chars failed: {r.stderr}"

            r = run_todo("list")
            assert r.returncode == 0
            assert f"1: {special}" in r.stdout, (
                f"Expected '1: {special}' in output, got: {r.stdout!r}"
            )
        finally:
            cleanup()
