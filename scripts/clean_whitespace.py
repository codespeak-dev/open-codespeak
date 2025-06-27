#!/usr/bin/env python3
"""
Script to clean empty lines with tabs/spaces from Python files.
Can be run standalone or integrated into the build process.
"""

import os
import sys
import glob
from typing import List


def clean_empty_lines_with_tabs(file_path: str) -> bool:
    """
    Remove empty lines that contain only tabs and/or spaces.
    Returns True if file was modified, False otherwise.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Remove lines that contain only whitespace
        cleaned_lines = []
        modified = False

        for line in lines:
            if line.strip() == '':  # Line contains only whitespace
                if line != '\n':  # If it's not just a newline, it has tabs/spaces
                    modified = True
                cleaned_lines.append('\n')  # Replace with clean newline
            else:
                cleaned_lines.append(line)

        if modified:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(cleaned_lines)
            return True

        return False

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def find_python_files(directory: str = ".") -> List[str]:
    """Find all Python files in the given directory recursively."""
    python_files = []
    skip_dirs = {'.git', '.venv', '__pycache__', '.pytest_cache', 'venv', 'env'}

    for root, dirs, files in os.walk(directory):
        # Skip unwanted directories
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))

    return python_files


def main():
    """Main function to clean Python files."""
    if len(sys.argv) > 1:
        # Clean specific files provided as arguments
        files_to_clean = sys.argv[1:]
    else:
        # Clean all Python files in current directory
        files_to_clean = find_python_files()

    modified_files = []

    for file_path in files_to_clean:
        if os.path.exists(file_path) and file_path.endswith('.py'):
            if clean_empty_lines_with_tabs(file_path):
                modified_files.append(file_path)
                print(f"Cleaned: {file_path}")

    if modified_files:
        print(f"\nCleaned {len(modified_files)} files:")
        for file_path in modified_files:
            print(f"  - {file_path}")
    else:
        print("No files needed cleaning.")


if __name__ == "__main__":
    main()