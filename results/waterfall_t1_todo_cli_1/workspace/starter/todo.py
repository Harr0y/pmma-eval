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
        todo_text = sys.argv[2]
        todos = load_todos()
        todos.append(todo_text)
        save_todos(todos)

    elif command == "list":
        todos = load_todos()
        for i, todo in enumerate(todos):
            print(f"{i + 1}: {todo}")

    elif command == "remove":
        if len(sys.argv) < 3:
            print("Usage: python todo.py remove <ID>")
            return
        try:
            idx = int(sys.argv[2]) - 1  # 转换为 0-based 索引
        except ValueError:
            return  # 非数字 ID，静默忽略
        todos = load_todos()
        if 0 <= idx < len(todos):
            todos.pop(idx)
            save_todos(todos)
        # ID 超出范围时静默忽略，不做任何操作

if __name__ == "__main__":
    main()
