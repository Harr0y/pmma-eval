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
        # 直接追加写入，不读取整个文件
        content = sys.argv[2]
        with open(DB_FILE, "a") as f:
            f.write(content + "\n")

    elif command == "list":
        todos = load_todos()
        for i, todo in enumerate(todos):
            print(f"{i + 1}: {todo}")

    elif command == "remove":
        idx = int(sys.argv[2])
        todos = load_todos()
        # 1-based index, so valid range is [1, len]
        if 1 <= idx <= len(todos):
            todos.pop(idx - 1)
            save_todos(todos)
        # 超出范围时静默忽略

if __name__ == "__main__":
    main()
