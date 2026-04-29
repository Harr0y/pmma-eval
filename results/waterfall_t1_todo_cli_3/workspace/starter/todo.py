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
        # ADD-1: load_todos() → append → save_todos()
        if len(sys.argv) < 3:
            print("Usage: python todo.py add \"task content\"")
            return
        todos = load_todos()
        todos.append(sys.argv[2])
        save_todos(todos)

    elif command == "list":
        # LIST-1: load_todos() → enumerate → print(f"{i+1}: {todo}")
        todos = load_todos()
        for i, todo in enumerate(todos):
            print(f"{i + 1}: {todo}")

    elif command == "remove":
        # REMOVE-1: parse ID → int conversion → range check → pop → save_todos()
        if len(sys.argv) < 3:
            print("Usage: python todo.py remove <ID>")
            return
        try:
            index = int(sys.argv[2]) - 1  # Convert to 0-based
        except (ValueError, IndexError):
            return  # Silently ignore non-numeric ID

        todos = load_todos()
        if 0 <= index < len(todos):
            todos.pop(index)
            save_todos(todos)
        # else: silently ignore out-of-range ID

if __name__ == "__main__":
    main()
