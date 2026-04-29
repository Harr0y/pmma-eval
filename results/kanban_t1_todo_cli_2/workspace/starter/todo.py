import sys
import os

# Data storage file
DB_FILE = "todos.txt"

def load_todos():
    if not os.path.exists(DB_FILE):
        return []
    with open(DB_FILE, "r") as f:
        return [line.strip() for line in f.readlines() if line.strip()]

def save_todos(todos):
    with open(DB_FILE, "w") as f:
        for todo in todos:
            f.write(todo + "\n")

def main():
    if len(sys.argv) < 2:
        print("Usage: python todo.py [add|list|remove] [args]")
        return

    command = sys.argv[1]

    if command == "add":
        if len(sys.argv) < 3:
            return
        todos = load_todos()
        todos.append(sys.argv[2])
        save_todos(todos)

    elif command == "list":
        todos = load_todos()
        for i, todo in enumerate(todos, start=1):
            print(f"{i}: {todo}")

    elif command == "remove":
        if len(sys.argv) < 3:
            return
        try:
            task_id = int(sys.argv[2])
        except ValueError:
            return
        todos = load_todos()
        # ID is 1-based; silently ignore if out of range
        if 1 <= task_id <= len(todos):
            todos.pop(task_id - 1)
            save_todos(todos)

if __name__ == "__main__":
    main()
