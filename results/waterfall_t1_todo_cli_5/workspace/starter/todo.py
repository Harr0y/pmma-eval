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
        # ADD-1.5: 缺少参数时静默忽略
        if len(sys.argv) < 3:
            return
        # ADD-1.1: 从 sys.argv[2] 获取任务内容
        content = sys.argv[2]
        # ADD-1.2: 使用 load_todos() 读取当前列表
        todos = load_todos()
        # ADD-1.3: 将任务内容 append 到列表末尾
        # ADD-1.6: 任务内容不做任何处理（原样保存特殊字符）
        todos.append(content)
        # ADD-1.4: 使用 save_todos() 写回文件
        save_todos(todos)

    elif command == "list":
        # LIST-1.1: 使用 load_todos() 读取当前列表
        # LIST-1.5: 文件不存在时 load_todos() 返回空列表
        todos = load_todos()
        # LIST-1.2: 使用 enumerate(todos, start=1) 生成 1-based ID
        # LIST-1.3: 格式为 "{idx}: {todo}"
        # LIST-1.4: 列表为空时 for 循环不执行，无输出
        for idx, todo in enumerate(todos, start=1):
            print(f"{idx}: {todo}")

    elif command == "remove":
        # REMOVE-1.2: 缺少参数时静默忽略
        if len(sys.argv) < 3:
            return
        # REMOVE-1.1: 从 sys.argv[2] 获取 ID 字符串
        # REMOVE-1.3: 转换为整数并减 1 得到 0-based 索引
        # REMOVE-1.4: 转换失败（非整数）时静默 return
        try:
            idx = int(sys.argv[2]) - 1
        except (ValueError, IndexError):
            return
        # REMOVE-1.5: 索引越界时静默忽略
        # REMOVE-1.6: 索引有效时，使用 pop(idx) 删除并 save_todos() 写回
        # REMOVE-1.7: 删除后列表自动重新编号（ID 基于列表索引）
        todos = load_todos()
        if 0 <= idx < len(todos):
            todos.pop(idx)
            save_todos(todos)

if __name__ == "__main__":
    main()
