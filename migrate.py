import subprocess
import sys

from phase_manager import State, Phase, Context
from with_step import with_step

class Migrate(Phase):
    description = "Run database migrations"

    def run(self, state: State, context: Context = None) -> dict:
        project_path = state["project_path"]

        def migrate():
            try:
                subprocess.run([sys.executable, "manage.py", "migrate"], cwd=project_path, check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                if e.stdout:
                    print(e.stdout.decode())
                if e.stderr:
                    print(e.stderr.decode())
                raise
        with with_step("Running migrate..."):
            migrate()
        print("migrate complete.")

        return {}