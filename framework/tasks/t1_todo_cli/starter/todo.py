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
    
    # 任务提示：请在此处实现具体的逻辑
    # 1. add "content" -> 追加到文件末尾
    # 2. list -> 打印 "ID: 内容"，ID 为 1-based 行号
    # 3. remove ID -> 根据行号删除
    
    pass

if __name__ == "__main__":
    main()
