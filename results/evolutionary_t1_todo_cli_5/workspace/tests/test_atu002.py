"""Tests for ATU-002: Remove command in todo.py.

ATU-002 scope:
- remove <ID> deletes a task by 1-based line number
- Remaining tasks are re-numbered after deletion
- Non-existent IDs are silently ignored (no crash, exit code 0)
- Remove from empty file does not crash
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


def add_tasks(*tasks):
    """Helper to add multiple tasks in order."""
    for task in tasks:
        r = run_todo("add", task)
        assert r.returncode == 0, f"add failed for '{task}': {r.stderr}"


class TestRemoveSingleTask:
    """Remove one task from a list and verify deletion + re-numbering."""

    def test_remove_middle_renumbers_correctly(self):
        cleanup()
        try:
            add_tasks("Alpha", "Beta", "Gamma")

            r = run_todo("remove", "2")
            assert r.returncode == 0, f"remove failed: {r.stderr}"

            r = run_todo("list")
            assert r.returncode == 0
            lines = r.stdout.strip().split("\n")
            assert lines == [
                "1: Alpha",
                "2: Gamma",
            ], f"Unexpected list after removing middle task: {lines!r}"
        finally:
            cleanup()

    def test_remove_first_renumbers_correctly(self):
        cleanup()
        try:
            add_tasks("First", "Second", "Third")

            r = run_todo("remove", "1")
            assert r.returncode == 0, f"remove failed: {r.stderr}"

            r = run_todo("list")
            assert r.returncode == 0
            lines = r.stdout.strip().split("\n")
            assert lines == [
                "1: Second",
                "2: Third",
            ], f"Unexpected list after removing first task: {lines!r}"
        finally:
            cleanup()

    def test_remove_last_renumbers_correctly(self):
        cleanup()
        try:
            add_tasks("One", "Two", "Three")

            r = run_todo("remove", "3")
            assert r.returncode == 0, f"remove failed: {r.stderr}"

            r = run_todo("list")
            assert r.returncode == 0
            lines = r.stdout.strip().split("\n")
            assert lines == [
                "1: One",
                "2: Two",
            ], f"Unexpected list after removing last task: {lines!r}"
        finally:
            cleanup()

    def test_removed_task_not_in_list(self):
        """After remove, the deleted task content should not appear in list output."""
        cleanup()
        try:
            add_tasks("Keep this", "Delete this", "Also keep")

            run_todo("remove", "2")

            r = run_todo("list")
            assert "Delete this" not in r.stdout, (
                f"Deleted task should not appear in list: {r.stdout!r}"
            )
        finally:
            cleanup()


class TestRemoveNonExistentId:
    """Removing an ID that does not exist should not crash and return code 0."""

    def test_remove_id_99_no_crash(self):
        cleanup()
        try:
            add_tasks("Only task")

            r = run_todo("remove", "99")
            assert r.returncode == 0, f"remove 99 should return 0, got {r.returncode}: {r.stderr}"

            # Original task should still be intact
            r = run_todo("list")
            assert "1: Only task" in r.stdout
        finally:
            cleanup()

    def test_remove_negative_id_no_crash(self):
        cleanup()
        try:
            add_tasks("Only task")

            r = run_todo("remove", "-1")
            assert r.returncode == 0, f"remove -1 should return 0, got {r.returncode}: {r.stderr}"
        finally:
            cleanup()

    def test_remove_zero_id_no_crash(self):
        cleanup()
        try:
            add_tasks("Only task")

            r = run_todo("remove", "0")
            assert r.returncode == 0, f"remove 0 should return 0, got {r.returncode}: {r.stderr}"
        finally:
            cleanup()


class TestRemoveFromEmptyFile:
    """Removing from an empty todo list should not crash."""

    def test_remove_from_empty_no_crash(self):
        cleanup()
        try:
            r = run_todo("remove", "1")
            assert r.returncode == 0, f"remove on empty file should return 0, got {r.returncode}: {r.stderr}"
        finally:
            cleanup()


class TestRemoveFullFlow:
    """End-to-end tests: add multiple, remove, list to verify."""

    def test_add_three_remove_first_list(self):
        cleanup()
        try:
            add_tasks("Task A", "Task B", "Task C")

            r = run_todo("remove", "1")
            assert r.returncode == 0

            r = run_todo("list")
            lines = r.stdout.strip().split("\n")
            assert lines == ["1: Task B", "2: Task C"], f"Unexpected output: {lines!r}"
        finally:
            cleanup()

    def test_add_three_remove_last_list(self):
        cleanup()
        try:
            add_tasks("Task A", "Task B", "Task C")

            r = run_todo("remove", "3")
            assert r.returncode == 0

            r = run_todo("list")
            lines = r.stdout.strip().split("\n")
            assert lines == ["1: Task A", "2: Task B"], f"Unexpected output: {lines!r}"
        finally:
            cleanup()

    def test_add_three_remove_middle_list(self):
        cleanup()
        try:
            add_tasks("Task A", "Task B", "Task C")

            r = run_todo("remove", "2")
            assert r.returncode == 0

            r = run_todo("list")
            lines = r.stdout.strip().split("\n")
            assert lines == ["1: Task A", "2: Task C"], f"Unexpected output: {lines!r}"
        finally:
            cleanup()

    def test_remove_all_tasks_one_by_one(self):
        cleanup()
        try:
            add_tasks("Only task")

            run_todo("remove", "1")

            r = run_todo("list")
            assert r.stdout.strip() == "", f"Expected empty output after removing all, got: {r.stdout!r}"
        finally:
            cleanup()
