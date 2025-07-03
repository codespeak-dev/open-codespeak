import subprocess
import sys
import logging
from colors import Colors
from phase_manager import State, Phase, Context

class MakeMigrations(Phase):
    description = "Create Django database migrations"

    def run(self, state: State, context: Context) -> dict:
        logger = logging.getLogger("MakeMigrations")
        project_path = state["project_path"]

        try:
            subprocess.run(
                [sys.executable, "manage.py", "makemigrations", "web"], 
                cwd=project_path, 
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            logger.info(f"  {Colors.BRIGHT_RED}✗{Colors.END} makemigrations failed:")
            if e.stdout:
                logger.info(f"    stdout: {e.stdout}")
            if e.stderr:
                logger.info(f"    stderr: {e.stderr}")
            raise
        return {}