import subprocess
import os
import pytest

def test_todo_edge_cases():
    # Cleanup
    if os.path.exists("todos.txt"):
        os.remove("todos.txt")

    # 1. List empty
    result = subprocess.run(["python3", "starter/todo.py", "list"], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == ""

    # 2. Remove non-existent
    # Should not crash, ideally show an error or just do nothing
    subprocess.run(["python3", "starter/todo.py", "remove", "99"], check=True)

    # 3. Add special characters
    subprocess.run(["python3", "starter/todo.py", "add", "Special !@#$%^&*()"], check=True)
    result = subprocess.run(["python3", "starter/todo.py", "list"], capture_output=True, text=True, check=True)
    assert "Special !@#$%^&*()" in result.stdout
