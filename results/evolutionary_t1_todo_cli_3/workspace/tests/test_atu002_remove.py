"""
ATU-002: todo.py remove command.

remove <ID> deletes the task at the given 1-based line number.
After removal, remaining tasks are renumbered starting from 1.
Non-existent IDs are silently ignored (returncode == 0, no side effects).
Boundary IDs (0, negative) do not crash.

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


def setup_tasks(*tasks):
    """Add a sequence of tasks via the add command."""
    for task in tasks:
        r = run_todo("add", task)
        assert r.returncode == 0, f"setup add failed for {task!r}: {r.stderr}"


# -- Fixtures ----------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_todos():
    """Ensure todos.txt is removed before and after each test."""
    cleanup()
    yield
    cleanup()


# -- Remove existing task ----------------------------------------------------


class TestRemoveExistingTask:
    def test_remove_existing_task_no_longer_shown(self):
        """After removing a task by ID, list should no longer display it."""
        setup_tasks("Task A", "Task B", "Task C")
        r = run_todo("remove", "2")
        assert r.returncode == 0, f"remove failed: {r.stderr}"

        r = run_todo("list")
        assert r.returncode == 0
        assert "Task B" not in r.stdout
        assert "1: Task A" in r.stdout
        assert "2: Task C" in r.stdout

    def test_remove_single_task_leaves_empty_list(self):
        """Removing the only task should result in an empty list."""
        setup_tasks("Only task")
        r = run_todo("remove", "1")
        assert r.returncode == 0

        r = run_todo("list")
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_remove_first_task_renumbers(self):
        """Deleting ID=1 should shift ID=2 to ID=1 and ID=3 to ID=2."""
        setup_tasks("Alpha", "Beta", "Gamma")
        r = run_todo("remove", "1")
        assert r.returncode == 0

        r = run_todo("list")
        assert r.returncode == 0
        lines = r.stdout.strip().split("\n")
        assert lines == ["1: Beta", "2: Gamma"]

    def test_remove_middle_task_renumbers(self):
        """Deleting a middle task should renumber the subsequent tasks."""
        setup_tasks("First", "Second", "Third")
        r = run_todo("remove", "2")
        assert r.returncode == 0

        r = run_todo("list")
        lines = r.stdout.strip().split("\n")
        assert lines == ["1: First", "2: Third"]

    def test_remove_last_task(self):
        """Deleting the last task should not affect earlier tasks."""
        setup_tasks("Keep", "Remove me")
        r = run_todo("remove", "2")
        assert r.returncode == 0

        r = run_todo("list")
        lines = r.stdout.strip().split("\n")
        assert lines == ["1: Keep"]

    def test_remove_returncode_zero(self):
        """remove command should exit with code 0 on success."""
        setup_tasks("Something")
        r = run_todo("remove", "1")
        assert r.returncode == 0, f"remove failed: {r.stderr}"


# -- Renumbering after removal ------------------------------------------------


class TestRenumberingAfterRemoval:
    def test_renumbering_after_remove_first(self):
        """After removing ID=1, original ID=2 becomes ID=1."""
        setup_tasks("A", "B", "C", "D")
        run_todo("remove", "1")
        r = run_todo("list")
        assert "1: B" in r.stdout
        assert "2: C" in r.stdout
        assert "3: D" in r.stdout
        assert "4:" not in r.stdout

    def test_renumbering_after_remove_middle(self):
        """After removing ID=2 from 4 tasks, IDs are 1, 2, 3."""
        setup_tasks("A", "B", "C", "D")
        run_todo("remove", "2")
        r = run_todo("list")
        assert "1: A" in r.stdout
        assert "2: C" in r.stdout
        assert "3: D" in r.stdout
        assert "4:" not in r.stdout

    def test_renumbering_after_remove_last(self):
        """After removing the last task, remaining IDs stay sequential."""
        setup_tasks("A", "B", "C")
        run_todo("remove", "3")
        r = run_todo("list")
        assert "1: A" in r.stdout
        assert "2: B" in r.stdout
        assert "3:" not in r.stdout


# -- Non-existent ID ---------------------------------------------------------


class TestRemoveNonExistentId:
    def test_remove_nonexistent_id_no_crash(self):
        """Removing a non-existent ID should not crash and return 0."""
        setup_tasks("Task A", "Task B")
        r = run_todo("remove", "99")
        assert r.returncode == 0, f"remove crashed: {r.stderr}"

    def test_remove_nonexistent_id_no_side_effects(self):
        """Removing a non-existent ID should leave the task list unchanged."""
        setup_tasks("Task A", "Task B", "Task C")
        run_todo("remove", "99")

        r = run_todo("list")
        assert r.returncode == 0
        lines = r.stdout.strip().split("\n")
        assert lines == ["1: Task A", "2: Task B", "3: Task C"]

    def test_remove_nonexistent_id_zero(self):
        """Removing ID=0 (which does not exist) should not crash."""
        setup_tasks("Task A", "Task B")
        r = run_todo("remove", "0")
        assert r.returncode == 0

    def test_remove_nonexistent_id_negative(self):
        """Removing a negative ID should not crash."""
        setup_tasks("Task A", "Task B")
        r = run_todo("remove", "-1")
        assert r.returncode == 0


# -- Boundary cases ----------------------------------------------------------


class TestRemoveBoundaryCases:
    def test_remove_id_zero_does_not_crash(self):
        """ID=0 is not a valid task ID; should not crash."""
        setup_tasks("Only task")
        r = run_todo("remove", "0")
        assert r.returncode == 0

        # Task list should be unchanged
        r = run_todo("list")
        assert "1: Only task" in r.stdout

    def test_remove_negative_id_does_not_crash(self):
        """Negative IDs should not crash and should not modify the list."""
        setup_tasks("Keep this")
        r = run_todo("remove", "-5")
        assert r.returncode == 0

        r = run_todo("list")
        assert "1: Keep this" in r.stdout

    def test_remove_non_numeric_id_does_not_crash(self):
        """Passing a non-numeric argument to remove should not crash."""
        setup_tasks("Keep this")
        r = run_todo("remove", "abc")
        assert r.returncode == 0

        r = run_todo("list")
        assert "1: Keep this" in r.stdout

    def test_remove_from_empty_list(self):
        """Removing any ID from an empty list should not crash."""
        r = run_todo("remove", "1")
        assert r.returncode == 0

    def test_remove_without_id_argument(self):
        """Calling remove without an ID argument should not crash."""
        setup_tasks("Task A")
        r = run_todo("remove")
        assert r.returncode == 0


# -- Sequential / consecutive removals ---------------------------------------


class TestConsecutiveRemovals:
    def test_remove_all_tasks_one_by_one(self):
        """Removing tasks one by one until empty; list should end up empty."""
        setup_tasks("A", "B", "C")
        run_todo("remove", "1")  # Remove A; list becomes [B, C]
        run_todo("remove", "1")  # Remove B; list becomes [C]
        run_todo("remove", "1")  # Remove C; list becomes []

        r = run_todo("list")
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_remove_first_then_last(self):
        """Remove first task, then remove the new last task."""
        setup_tasks("Alpha", "Beta", "Gamma", "Delta")
        run_todo("remove", "1")   # Remove Alpha -> [Beta, Gamma, Delta]
        run_todo("remove", "3")   # Remove Delta  -> [Beta, Gamma]

        r = run_todo("list")
        lines = r.stdout.strip().split("\n")
        assert lines == ["1: Beta", "2: Gamma"]

    def test_remove_middle_then_first(self):
        """Remove a middle task, then the first task, verify renumbering."""
        setup_tasks("W", "X", "Y", "Z")
        run_todo("remove", "2")   # Remove X -> [W, Y, Z]
        run_todo("remove", "1")   # Remove W -> [Y, Z]

        r = run_todo("list")
        lines = r.stdout.strip().split("\n")
        assert lines == ["1: Y", "2: Z"]

    def test_remove_multiple_interleaved_with_nonexistent(self):
        """Interleave valid and invalid removes; only valid ones take effect."""
        setup_tasks("P", "Q", "R")
        run_todo("remove", "99")  # no-op
        run_todo("remove", "2")   # Remove Q -> [P, R]
        run_todo("remove", "-1")  # no-op
        run_todo("remove", "1")   # Remove P -> [R]

        r = run_todo("list")
        lines = r.stdout.strip().split("\n")
        assert lines == ["1: R"]

    def test_remove_id_after_renumbering(self):
        """After removal and renumbering, the new IDs are the valid ones."""
        setup_tasks("One", "Two", "Three")
        run_todo("remove", "1")   # Remove One -> [Two, Three]
        # Now Two is ID=1 and Three is ID=2
        run_todo("remove", "1")   # Remove Two -> [Three]

        r = run_todo("list")
        lines = r.stdout.strip().split("\n")
        assert lines == ["1: Three"]


# -- Empty list after removal ------------------------------------------------


class TestEmptyListAfterRemoval:
    def test_list_empty_after_removing_all_tasks(self):
        """list should produce no output after all tasks are removed."""
        setup_tasks("Solo")
        run_todo("remove", "1")

        r = run_todo("list")
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_list_empty_after_removing_all_from_multiple(self):
        """list should produce no output after removing all tasks from a list of several."""
        setup_tasks("A", "B")
        run_todo("remove", "1")
        run_todo("remove", "1")

        r = run_todo("list")
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_list_empty_returncode_zero(self):
        """list on empty file after removal should still return 0."""
        setup_tasks("Temporary")
        run_todo("remove", "1")

        r = run_todo("list")
        assert r.returncode == 0


# -- File integrity ----------------------------------------------------------


class TestRemoveFileIntegrity:
    def test_no_trailing_blank_lines_in_file(self):
        """After removal, todos.txt should not have trailing blank lines."""
        setup_tasks("A", "B", "C")
        run_todo("remove", "2")

        with open(DB_FILE) as f:
            lines = f.readlines()

        # Every line should have content (no blank lines)
        for line in lines:
            assert line.strip() != "", f"Unexpected blank line in file: {lines!r}"

    def test_file_has_correct_content_after_remove(self):
        """The file should contain exactly the remaining tasks, one per line."""
        setup_tasks("Keep1", "Remove", "Keep2")
        run_todo("remove", "2")

        with open(DB_FILE) as f:
            content_lines = [l.strip() for l in f.readlines() if l.strip()]

        assert content_lines == ["Keep1", "Keep2"]

    def test_file_deleted_when_all_removed(self):
        """todos.txt should still exist but be empty after removing all tasks."""
        setup_tasks("Only")
        run_todo("remove", "1")

        with open(DB_FILE) as f:
            content = f.read().strip()
        assert content == ""
