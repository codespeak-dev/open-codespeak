import subprocess
import sys

from phase_manager import State, Phase, Context
from with_step import with_step


class Migrate(Phase):
    def run(self, state: State, context: Context = None) -> dict:
        project_path = state["project_path"]

        def migrate():
            subprocess.run([sys.executable, "manage.py", "migrate"], cwd=project_path, check=True)
        with with_step("Running migrate..."):
            migrate()
        print("migrate complete.")

        return {}