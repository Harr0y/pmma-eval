import sys

# Data storage file
DB_FILE = "todos.txt"


def main():
    if len(sys.argv) < 2:
        print("Usage: python todo.py [add|list|remove] [args]")
        return

    command = sys.argv[1]

    if command == "add":
        if len(sys.argv) < 3:
            print("Usage: python todo.py add \"任务内容\"")
            return
        # Strategy: append mode — write a single line without reading the whole file
        task = sys.argv[2]
        with open(DB_FILE, "a") as f:
            f.write(task + "\n")

    elif command == "list":
        try:
            with open(DB_FILE, "r") as f:
                lines = f.readlines()
        except FileNotFoundError:
            return  # No file = no tasks, silent empty output
        for idx, line in enumerate(lines, start=1):
            stripped = line.rstrip("\n")
            if stripped:  # skip blank lines
                print(f"{idx}: {stripped}")

    elif command == "remove":
        if len(sys.argv) < 3:
            print("Usage: python todo.py remove <ID>")
            return
        try:
            target_id = int(sys.argv[2])
        except ValueError:
            return  # non-integer ID, silently ignore
        try:
            with open(DB_FILE, "r") as f:
                lines = f.readlines()
        except FileNotFoundError:
            return  # no file, nothing to remove
        # Filter: skip the line at target_id (1-based)
        new_lines = [line for i, line in enumerate(lines, start=1) if i != target_id]
        with open(DB_FILE, "w") as f:
            f.writelines(new_lines)

    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
