from pathlib import Path
from file_based_cache import Sanitizer


class PathSanitizer(Sanitizer):
    def __init__(self, base_dir: str):
        self.base_dir = base_dir

    def sanitize(self, text: str) -> str:
        base_path = Path(self.base_dir)
        return text.replace(str(base_path.absolute()), "[BASE_DIR]").replace(str(base_path), "[BASE_DIR]").replace(str(Path.home()), "[HOME]")


class SubstringBasedSanitizer:
    def __init__(self, substrings: list[tuple[str, str]]):
        """
        substrings is a list of tuples of substrings to replace with their values.
        The substrings are replaced in the order they are given.
        """
        self.substrings = substrings

    def sanitize(self, text: str) -> str:
        for pattern, replacement in self.substrings:
            text = text.replace(pattern, replacement)
        return text


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

    test2 = "\n<context name=\"project_structure\">\n\u251c\u2500\u2500 27_helloworld/\n\u2502   \u251c\u2500\u2500 __init__.py\n\u2502   \u251c\u2500\u2500 asgi.py\n\u2502   \u251c\u2500\u2500 settings.py\n\u2502   \u251c\u2500\u2500 urls.py\n\u2502   \u2514\u2500\u2500 wsgi.py\n\u251c\u2500\u2500 db.sqlite3\n\u251c\u2500\u2500 entities.json\n\u251c\u2500\u2500 manage.py\n\u251c\u2500\u2500 templates/\n\u2502   \u2514\u2500\u2500 layouts/\n\u2502       \u2514\u2500\u2500 base.html\n\u2514\u2500\u2500 web/\n    \u251c\u2500\u2500 __init__.py\n    \u251c\u2500\u2500 admin.py\n    \u251c\u2500\u2500 apps.py\n    \u251c\u2500\u2500 models.py\n    \u251c\u2500\u2500 tests.py\n    \u2514\u2500\u2500 views.py\n\n</context>\n<context name=\"general_facts\">\n- The project is named \"HelloWorld\".\n- It is a Django application.\n- The application only responds to the root route (/).\n- The application is styled with TailwindCSS.\n- The main functionality is to display a \"hello world\" message.\n- The application has a single screen/page (the homepage).\n</context>\n<context name=\"models\" path=\"web/models.py\">\n1\tfrom django.db import models\n2\t\n</context>\n<context name=\"urls\" path=\"web/urls.py\">\n\n</context>\n<step><overall_goal>\n    Create a Django application that displays a \"Hello World\" message on the homepage for visitors.\n</overall_goal>\n\n<key_knowledge>\n    \u2022 This is a simple Django web application with a single homepage view\n    \u2022 The homepage should be accessible at the root URL pattern \"/\"\n    \u2022 The message should be styled using TailwindCSS\n    \u2022 No user authentication or complex functionality is required\n    \u2022 This is the foundational step for the application\n</key_knowledge>\n\n<current_plan>\n    \u2022 Set up Django project structure and basic configuration\n    \u2022 Create a view function to handle the homepage request\n    \u2022 Create an HTML template that displays \"Hello World\" message\n    \u2022 Configure URL routing to map \"/\" to the homepage view\n    \u2022 Integrate TailwindCSS for styling the message\n    \u2022 Test the homepage functionality\n</current_plan></step>\n"
    print(SubstringBasedSanitizer([
        ("/Users/abreslav/codespeak/open-codespeak/", "[PROJECT_PATH]"),
        ("/Users/abreslav/codespeak/open-codespeak", "[PROJECT_PATH]"),
        ("27_helloworld/", "[PROJECT_NAME]"),
        ("/Users/abreslav/.local/share/uv/python/cpython-3.11.13-macos-aarch64-none/lib/python3.11", "[HOME]"),
    ]).sanitize(test2))