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
        # Expect exactly one argument after "add"
        if len(sys.argv) < 3:
            print("Usage: python todo.py add \"task content\"")
            return
        task_content = sys.argv[2]
        todos = load_todos()
        todos.append(task_content)
        save_todos(todos)

    elif command == "list":
        todos = load_todos()
        # Empty list produces no output — satisfies "no output when empty"
        for idx, todo in enumerate(todos, start=1):
            print(f"{idx}: {todo}")

    elif command == "remove":
        if len(sys.argv) < 3:
            return
        try:
            task_id = int(sys.argv[2])
        except ValueError:
            return
        todos = load_todos()
        if 1 <= task_id <= len(todos):
            del todos[task_id - 1]
            save_todos(todos)

if __name__ == "__main__":
    main()
