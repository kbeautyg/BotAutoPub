import os

# List of file paths to create according to the given project structure
paths = [
    "bot.py",
    "config.py",
    "database.py",
    "handlers/__init__.py",
    "handlers/common.py",
    "handlers/channel_management.py",
    "handlers/post_creation.py",
    "handlers/post_management.py",
    "scheduler.py",
    "utils.py",
    ".env",
    "requirements.txt",
    "README.md",
]

# Create directories and files
for file_path in paths:
    dir_path = os.path.dirname(file_path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        pass  # Create an empty file

print("Project structure created successfully.")
