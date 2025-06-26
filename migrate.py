import subprocess
import sys

from state_machine import State, Transition
from with_step import with_step


class Migrate(Transition):
    def run(self, state: State) -> State:
        project_path = state.data["project_path"]

        def migrate():
            subprocess.run([sys.executable, "manage.py", "migrate"], cwd=project_path, check=True)
        with with_step("Running migrate..."):
            migrate()
        print("migrate complete.")
        
        return state.clone()