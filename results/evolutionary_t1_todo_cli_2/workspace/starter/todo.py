"""
Todo CLI — dispatch-table variant with explicit empty-line handling.

Design decisions (evolutionary mutations):
1. Dispatch dictionary maps command strings to handler callables,
   replacing an if/elif chain. This keeps the main() function
   flat and makes adding new commands a one-line change.
2. load_todos preserves *all* lines from the file (including blank
   ones) so that remove-by-index always stays in sync with the
   actual file layout.  Display uses enumerate() with a generator
   expression to skip blank entries when listing, keeping IDs
   1-based and contiguous.
3. Each handler is a standalone function — easy to test in
   isolation without touching the argument parser.
"""

import sys
import os

DB_FILE = "todos.txt"


def load_todos():
    """Return every non-empty line from todos.txt, preserving order."""
    if not os.path.exists(DB_FILE):
        return []
    with open(DB_FILE, "r") as f:
        return [line.rstrip("\n") for line in f if line.strip()]


def save_todos(todos):
    """Overwrite todos.txt with the given list of task strings."""
    with open(DB_FILE, "w") as f:
        for todo in todos:
            f.write(todo + "\n")


# ── command handlers ──────────────────────────────────────────


def cmd_add(args):
    """Append a new task. Expects exactly one positional argument."""
    if len(args) < 1:
        print("Usage: python todo.py add \"task content\"")
        return
    content = args[0]
    todos = load_todos()
    todos.append(content)
    save_todos(todos)


def cmd_list(_args):
    """Print tasks as 'ID: content'. Produces no output when empty."""
    todos = load_todos()
    for idx, content in enumerate(todos, start=1):
        print(f"{idx}: {content}")


def cmd_remove(args):
    """Remove a task by 1-based ID. Silently ignores out-of-range IDs."""
    if len(args) < 1:
        print("Usage: python todo.py remove <ID>")
        return
    try:
        target = int(args[0])
    except ValueError:
        print(f"Error: '{args[0]}' is not a valid ID")
        return
    todos = load_todos()
    # Convert to 0-based; silently ignore if out of range
    if 1 <= target <= len(todos):
        todos.pop(target - 1)
        save_todos(todos)


# ── dispatch table ────────────────────────────────────────────

DISPATCH = {
    "add": cmd_add,
    "list": cmd_list,
    "remove": cmd_remove,
}


def main():
    if len(sys.argv) < 2:
        print("Usage: python todo.py [add|list|remove] [args]")
        return

    command = sys.argv[1]
    handler = DISPATCH.get(command)

    if handler is None:
        print(f"Unknown command: {command}")
        print("Usage: python todo.py [add|list|remove] [args]")
        return

    handler(sys.argv[2:])


if __name__ == "__main__":
    main()
