import os
import subprocess
import sys

from colors import Colors

from phase_manager import State, Phase, Context

class MakeMigrations(Phase):
    description = "Create Django database migrations"

    def run(self, state: State, context: Context) -> dict:
        project_path = state["project_path"]

        try:
            result = subprocess.run(
                [sys.executable, "manage.py", "makemigrations", "web"], 
                cwd=project_path, 
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            print(f"  {Colors.BRIGHT_RED}✗{Colors.END} makemigrations failed:")
            if e.stdout:
                print(f"    stdout: {e.stdout}")
            if e.stderr:
                print(f"    stderr: {e.stderr}")
            raise
        return {}