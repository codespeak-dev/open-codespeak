from pathlib import Path
from file_based_cache import Sanitizer


class PathSanitizer(Sanitizer):
    def __init__(self, base_dir: str):
        self.base_dir = base_dir

    def sanitize(self, text: str) -> str:
        base_path = Path(self.base_dir)
        return text.replace(str(base_path.absolute()), "[BASE_DIR]").replace(str(base_path), "[BASE_DIR]").replace(str(Path.home()), "[HOME]")

if __name__ == "__main__":
    print(
        PathSanitizer("/Users/abreslav/codespeak/open-codespeak").sanitize( 
                       "/Users/abreslav/codespeak/open-codespeak/test_outputs/.llm_cache/4d5371325cdcb3c9f6267ee7fe8139b9156f6989648f6d6b1fb2a3abd63188d9.src.json"))
    test = """Error output:
Traceback (most recent call last):
  File \"/Users/abreslav/codespeak/open-codespeak/test_outputs/28_lumama/manage.py\", line 20, in <module>
    main()
  File \"/Users/abreslav/codespeak/open-codespeak/test_outputs/28_lumama/manage.py\", line 17, in main
    execute_from_command_line(sys.argv)
  File \"/Users/abreslav/codespeak/open-codespeak/.venv/lib/python3.11/site-packages/django/core/management/__init__.py\", line 442, in execute_from_command_line
    utility.execute()
  File \"/Users/abreslav/codespeak/open-codespeak/.venv/lib/python3.11/site-packages/django/core/management/__init__.py\", line 416, in execute
    django.setup()
  File \"/Users/abreslav/codespeak/open-codespeak/.venv/lib/python3.11/site-packages/django/__init__.py\", line 24, in setup
    apps.populate(settings.INSTALLED_APPS)
  File \"/Users/abreslav/codespeak/open-codespeak/.venv/lib/python3.11/site-packages/django/apps/registry.py\", line 116, in populate
    app_config.import_models()
  File \"/Users/abreslav/codespeak/open-codespeak/.venv/lib/python3.11/site-packages/django/apps/config.py\", line 269, in import_models
    self.models_module = import_module(models_module_name)
                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File \"/Users/abreslav/.local/share/uv/python/cpython-3.11.13-macos-aarch64-none/lib/python3.11/importlib/__init__.py\", line 126, in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File \"<frozen importlib._bootstrap>\", line 1204, in _gcd_import
  File \"<frozen importlib._bootstrap>\", line 1176, in _find_and_load
  File \"<frozen importlib._bootstrap>\", line 1147, in _find_and_load_unlocked
  File \"<frozen importlib._bootstrap>\", line 690, in _load_unlocked
  File \"<frozen importlib._bootstrap_external>\", line 940, in exec_module
  File \"<frozen importlib._bootstrap>\", line 241, in _call_with_frames_removed
  File \"/Users/abreslav/codespeak/open-codespeak/test_outputs/28_lumama/web/models.py\", line 13, in <module>
    class Event(models.Model):
  File \"/Users/abreslav/codespeak/open-codespeak/test_outputs/28_lumama/web/models.py\", line 27, in Event
    uuid = models.UUIDField(default=uuid.uuid4, unique=True)
                                    ^^^^
NameError: name 'uuid' is not defined
"""
    print(PathSanitizer("test_outputs/28_lumama").sanitize(test))