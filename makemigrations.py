import os
import subprocess
import sys

import anthropic

from colors import Colors
from with_step import with_step

from state_machine import State, Transition, Context


def add_import_to_file(file_path: str, import_statement: str):
    """
    Add an import statement to the top of a Python file after existing imports.
    """
    with open(file_path, 'r') as f:
        lines = f.readlines()

    # Find the last import line
    last_import_index = 0
    for i, line in enumerate(lines):
        if line.strip().startswith(('import ', 'from ')) and not line.strip().startswith('#'):
            last_import_index = i

    # Insert the new import after the last import
    if import_statement.strip() + '\n' not in lines:
        lines.insert(last_import_index + 1, import_statement.strip() + '\n')

        with open(file_path, 'w') as f:
            f.writelines(lines)        

def fix_missing_imports(error_output: str, models_file_path: str) -> bool:
    """
    Use Claude to detect missing imports from error output and fix them using tool calls.
    Returns True if fixes were applied, False otherwise.
    """
    client = anthropic.Anthropic()
    system_prompt = (
        "You are an expert Python/Django developer. Given an error output from Django makemigrations, "
        "identify any missing import statements needed to fix NameError issues. "
        "Use the add_import tool to add each missing import statement. "
        "Only call the tool for imports that are actually needed to fix the errors."
    )

    tools = [
        {
            "name": "add_import",
            "description": "Add an import statement to fix missing imports",
            "input_schema": {
                "type": "object",
                "properties": {
                    "import_statement": {
                        "type": "string",
                        "description": "The complete import statement (e.g., 'import uuid' or 'from django.contrib.auth.models import User')"
                    }
                },
                "required": ["import_statement"]
            }
        }
    ]

    response = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=512,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Error output:\n{error_output}"}],
        tools=tools
    )

    applied_fixes = False
    for content_block in response.content:
        if content_block.type == "tool_use" and content_block.name == "add_import":
            import_statement = content_block.input["import_statement"]
            print(f"    {Colors.BRIGHT_CYAN}+{Colors.END} {import_statement}")
            add_import_to_file(models_file_path, import_statement)
            applied_fixes = True

    return applied_fixes

class MakeMigrations(Transition):
    def run(self, state: State, context: Context = None) -> dict:
        project_path = state["project_path"]

        def makemigrations():
            max_retries = 3
            models_file_path = os.path.join(project_path, "web", "models.py")

            for attempt in range(max_retries):
                try:
                    result = subprocess.run(
                        [sys.executable, "manage.py", "makemigrations", "web"], 
                        cwd=project_path, 
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    return  # Success
                except subprocess.CalledProcessError as e:
                    print(f"  {Colors.BRIGHT_RED}✗{Colors.END} makemigrations failed:")
                    if e.stdout:
                        print(f"    stdout: {e.stdout}")
                    if e.stderr:
                        print(f"    stderr: {e.stderr}")

                    if attempt < max_retries - 1 and "NameError" in e.stderr:
                        print(f"  {Colors.BRIGHT_YELLOW}→{Colors.END} Detected missing imports, auto-fixing...")
                        if fix_missing_imports(e.stderr, models_file_path):
                            print(f"  {Colors.BRIGHT_GREEN}✓{Colors.END} Imports fixed, retrying...")
                            continue  # Retry with fixed imports
                    # Re-raise the error if we can't fix it or max retries reached                    
                    raise        
        with with_step("Running makemigrations for 'web' app..."):
            makemigrations()
        print("makemigrations complete.")

        return {}