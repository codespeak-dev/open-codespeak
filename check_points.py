from contextlib import contextmanager
import datetime
import json
import os
from typing import Any


PROJECT_NAME_EXTRACTED = "project_name_extracted"
ENTITIES_EXTRACTED = "entities_extracted"
DJANGO_PROJECT_CREATED = "django_project_created"
MAKEMIGRATIONS_COMPLETE = "makemigrations_complete"
MIGRATIONS_COMPLETE = "migrations_complete"
DONE = "done"

CHECK_POINT_ORDERING = [
    PROJECT_NAME_EXTRACTED,
    ENTITIES_EXTRACTED,
    DJANGO_PROJECT_CREATED,
    MAKEMIGRATIONS_COMPLETE,
    MIGRATIONS_COMPLETE,
    DONE,
]

class CheckPoint:
    pass

class CheckPoints:

    def __init__(self, target_dir: str, spec_file: str | None = None):
        self.target_dir = target_dir        
        self.checkpoints_file = os.path.join(self.target_dir, "codespeak_checkpoints.json")
        self.spec_file = spec_file or self.load(must_exist=True)["spec_file"]

    def save(self, name: str, data: dict = None):
        old_checkpoints = self.load()
        checkpoints = {
            **old_checkpoints,
            "spec_file": self.spec_file,
            "current": name,
            "data": {**old_checkpoints.get("data", {}), **(data or {})},
            "history": old_checkpoints.get("history", []) + [
                {"name": name, "timestamp": datetime.datetime.now().isoformat()}
            ],            
        }

        with open(self.checkpoints_file, "w") as f:
            json.dump(checkpoints, f, indent=4)

    def load(self, must_exist: bool = False):
        if not os.path.exists(self.checkpoints_file):
            if must_exist:
                raise FileNotFoundError(f"Checkpoints file {self.checkpoints_file} does not exist")
            return {}
        with open(self.checkpoints_file, "r") as f:
            return json.load(f)

    def data(self) -> dict:
        return self.load()["data"]

    def data(self, property: str) -> Any:
        return self.load()["data"][property]

    def get_current(self) -> str | None:
        return self.load().get("current", None)

    def should_run(self, name: str) -> bool:
        current = self.get_current()
        if current is None:
            return True
        return name not in CHECK_POINT_ORDERING or CHECK_POINT_ORDERING.index(name) > CHECK_POINT_ORDERING.index(current)

    @contextmanager
    def checkpoint(self, name: str, results_file: str | None = None):
        # print(f"Entering checkpoint {name}")
        should_run = self.should_run(name)
        if not should_run:
            print(f"Skipping checkpoint {name} because it has already been run")
        yield CheckPoint(self, name, should_run, results_file)
        if should_run:
            self.save(name)
        # print(f"Exiting checkpoint {name}")

class CheckPoint:
    def __init__(self, manager: CheckPoints, name: str, should_run: bool, results_file: str | None = None):
        self.name = name
        self.manager = manager
        self.should_run = should_run
        self._result = None
        self.results_path = os.path.join(self.manager.target_dir, results_file) if results_file else None

    @property
    def result(self) -> Any:
        if self._result is None:
            with open(self.results_path, "r") as f:
                self._result = json.load(f)
        return self._result

    @result.setter
    def result(self, result: Any):
        self._result = result
        with open(self.results_path, "w") as f:
            json.dump(result, f, indent=4, ensure_ascii=False)
