from contextlib import contextmanager
import datetime
import json
import os


PROJECT_NAME_EXTRACTED = "project_name_extracted"
ENTITIES_EXTRACTED = "entities_extracted"
DJANGO_PROJECT_CREATED = "django_project_created"
MAKEMIGRATIONS_COMPLETE = "makemigrations_complete"
MIGRATIONS_COMPLETE = "migrations_complete"
DONE = "done"

class CheckPoints:

    def __init__(self, target_dir: str, spec_file: str | None):
        self.target_dir = target_dir        
        self.checkpoints_file = os.path.join(self.target_dir, "codespeak_checkpoints.json")
        self.spec_file = spec_file or self.load(must_exist=True)["spec_file"]

    def save(self, name: str):
        checkpoints = self.load()
        checkpoints["spec_file"] = self.spec_file
        checkpoints["current"] = name
        checkpoints["history"] = checkpoints.get("history", []) + [
            {"name": name, "timestamp": datetime.datetime.now().isoformat()}
        ]

        with open(self.checkpoints_file, "w") as f:
            json.dump(checkpoints, f, indent=4)

    def load(self, must_exist: bool = False):
        if not os.path.exists(self.checkpoints_file):
            if must_exist:
                raise FileNotFoundError(f"Checkpoints file {self.checkpoints_file} does not exist")
            return {}
        with open(self.checkpoints_file, "r") as f:
            return json.load(f)

    def get_current(self) -> str | None:
        return self.load().get("current", None)

    @contextmanager
    def checkpoint(self, name: str):
        # print(f"Entering checkpoint {name}")
        yield
        self.save(name)
        # print(f"Exiting checkpoint {name}")
