import subprocess
import sys
import logging

from phase_manager import State, Phase, Context
from with_step import with_step

class Migrate(Phase):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__class__.__qualname__)
    description = "Run database migrations"

    def run(self, state: State, context: Context) -> dict:
        project_path = state["project_path"]

        def migrate():
            try:
                subprocess.run([sys.executable, "manage.py", "migrate"], cwd=project_path, check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                if e.stdout:
                    self.logger.info(e.stdout.decode())
                if e.stderr:
                    self.logger.info(e.stderr.decode())
                raise
        with with_step("Running migrate..."):
            migrate()
        self.logger.info("migrate complete.")

        return {}