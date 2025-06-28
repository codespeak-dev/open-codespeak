import shutil
from typing import List
import os
import secrets
from jinja2 import Environment, FileSystemLoader

from extract_entities import Entity
from state_machine import State, Transition, Context


def generate_django_project_from_template(target_dir: str, project_name: str, entities: List[Entity], app_name: str = "web"):
    template_dir = "app_template"
    project_root = os.path.join(target_dir, project_name)
    shutil.copytree(template_dir, project_root, dirs_exist_ok=True)

    shutil.move(
        os.path.join(project_root, '_project_'),
        os.path.join(project_root, project_name)
    )

    secret_key = secrets.token_urlsafe(50)
    env = Environment(loader=FileSystemLoader(project_root))
    context = {
        'project_name': project_name,
        'app_name': app_name,
        'secret_key': secret_key,
        'entities': entities
    }

    def render_and_write(template_path, output_path):
        template = env.get_template(template_path)
        content = template.render(context)
        with open(output_path, 'w') as f:
            f.write(content)


    project_settings_root = os.path.join(project_root, project_name)
    files_to_template = [
        # (template_path, output_path)
        (f'{project_name}/settings.py', os.path.join(project_settings_root, 'settings.py')),
        (f'{app_name}/models.py', os.path.join(project_root, app_name, 'models.py')),
        (f'{app_name}/views.py', os.path.join(project_root, app_name, 'views.py')),
        (f'{project_name}/asgi.py', os.path.join(project_settings_root, 'asgi.py')),
        (f'{project_name}/wsgi.py', os.path.join(project_settings_root, 'wsgi.py')),
        ('manage.py', os.path.join(project_root, 'manage.py')),
    ]

    for template_path, output_path in files_to_template:
        render_and_write(template_path, output_path)

class GenerateDjangoProject(Transition):
    def run(self, state: State, context: Context = None) -> dict:
        project_name = state["project_name"]
        target_dir = state["target_dir"]
        entities = state["entities"]
        print(f"Generating Django project in {target_dir} with name {project_name}")
        generate_django_project_from_template(target_dir, project_name, entities, "web")
        return {}

    def cleanup(self, state: State, context: Context = None):
        target_dir = state["target_dir"]
        project_name = state["project_name"]

        def rm(settings_path):
            if os.path.exists(settings_path):
                if os.path.isdir(settings_path):
                    shutil.rmtree(settings_path)
                else:
                    os.remove(settings_path)
                print(f"* Removed {settings_path}")

        rm(os.path.join(target_dir, project_name, project_name))
        rm(os.path.join(target_dir, project_name, "web"))
        rm(os.path.join(target_dir, project_name, "manage.py"))

