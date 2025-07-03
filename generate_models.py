import os
import re
from typing import List
from jinja2 import Environment, FileSystemLoader

from extract_entities import Entity
from phase_manager import State, Phase, Context


def generate_models_from_template(project_path: str, project_name: str, entities: List[Entity], app_name: str = "web"):
    env = Environment(loader=FileSystemLoader('app_template'))
    context = {
        'project_name': project_name,
        'app_name': app_name,
        'entities': entities
    }

    def render_and_write(template_path, output_path):
        template = env.get_template(template_path)
        content = template.render(context)
        # Remove excessive consecutive newlines (3+ becomes 2)
        content = re.sub(r'\n{3,}', '\n\n', content)
        with open(output_path, 'w') as f:
            f.write(content)

    files_to_template = [
        # (template_path, output_path)
        (f'{app_name}/models.py', os.path.join(project_path, app_name, 'models.py')),
        (f'{app_name}/views.py', os.path.join(project_path, app_name, 'views.py')),
    ]

    for template_path, output_path in files_to_template:
        render_and_write(template_path, output_path)


class GenerateModels(Phase):
    description = "Generate Django models from extracted entities"
    
    def run(self, state: State, context: Context = None) -> dict:
        project_name = state["project_name"]
        project_path = state["project_path"]
        entities = state["entities"]
        print(f"Generating Django models in {project_path}")
        generate_models_from_template(project_path, project_name, entities, "web")
        return {}