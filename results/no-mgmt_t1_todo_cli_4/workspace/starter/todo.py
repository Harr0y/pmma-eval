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
            print("Usage: python todo.py add \"任务内容\"")
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
            print("Usage: python todo.py remove <ID>")
            return
        todos = load_todos()
        idx = int(sys.argv[2]) - 1
        if 0 <= idx < len(todos):
            todos.pop(idx)
            save_todos(todos)

    else:
        print(f"Unknown command: {command}")

if __name__ == "__main__":
    main()
