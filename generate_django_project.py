import shutil
import os
import secrets
import re
from jinja2 import Environment, FileSystemLoader

from phase_manager import State, Phase, Context

def generate_django_project_from_template(project_path: str, project_name: str, app_name: str = "web"):
    template_dir = "app_template"
    
    # Copy template directory but exclude model-related files
    def ignore_model_templates(dir, files):
        if os.path.basename(dir) == app_name:
            return ['models.py', 'views.py']
        return []
    
    shutil.copytree(template_dir, project_path, dirs_exist_ok=True, ignore=ignore_model_templates)

    shutil.move(
        os.path.join(project_path, '_project_'),
        os.path.join(project_path, project_name)
    )

    secret_key = secrets.token_urlsafe(50)
    env = Environment(loader=FileSystemLoader(project_path))
    context = {
        'project_name': project_name,
        'app_name': app_name,
        'secret_key': secret_key,
    }

    def render_and_write(template_path, output_path):
        template = env.get_template(template_path)
        content = template.render(context)
        # Remove excessive consecutive newlines (3+ becomes 2)
        content = re.sub(r'\n{3,}', '\n\n', content)
        with open(output_path, 'w') as f:
            f.write(content)


    project_settings_root = os.path.join(project_path, project_name)
    files_to_template = [
        # (template_path, output_path)
        (f'{project_name}/settings.py', os.path.join(project_settings_root, 'settings.py')),
        (f'{project_name}/asgi.py', os.path.join(project_settings_root, 'asgi.py')),
        (f'{project_name}/wsgi.py', os.path.join(project_settings_root, 'wsgi.py')),
        ('manage.py', os.path.join(project_path, 'manage.py')),
    ]

    for template_path, output_path in files_to_template:
        render_and_write(template_path, output_path)

class GenerateDjangoProject(Phase):
    description = "Create a new Django project"
    
    def run(self, state: State, context: Context) -> dict:
        project_name = state["project_name"]
        project_path = state["project_path"]

        if os.path.exists(project_path) and os.path.exists(os.path.join(project_path, "manage.py")):
            print(f"Django project already exists at {project_path}, skipping generation")
            return {}

        print(f"Generating Django project in {project_path} with name {project_name}")
        generate_django_project_from_template(project_path, project_name, "web")
        return {}


