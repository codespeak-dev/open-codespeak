import os
import re
import json
import llm_cache
import logging
from jinja2 import Environment, FileSystemLoader
from fileutils import load_template as load_template_jinja, LLMFileGenerator

from extract_entities import Entity, to_entities
from phase_manager import State, Phase, Context

def generate_models_from_template(project_path: str, project_name: str, entities: list[Entity], app_name: str = "web"):
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


def generate_models_with_llm(project_path: str, old_models: str, old_entities: list[dict], new_entities: list[dict]):
    client = llm_cache.Anthropic()

    system_prompt = """
    You are an expert Django developer.
    """

    user_prompt = load_template_jinja("prompts/generate_models_incremental.j2", old_models=old_models, old_entities=old_entities, new_entities=new_entities)
    
    generator = LLMFileGenerator(max_tokens=10000)
    output_file_path = os.path.join(project_path, "web/models.py")
    
    generator.generate_and_write(
        client,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        expected_file_path="web/models.py",
        output_file_path=output_file_path
    )

class GenerateModels(Phase):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__class__.__qualname__)
    description = "Generate Django models from extracted entities"
    
    def run(self, state: State, context: Context) -> dict:
        project_path = state["project_path"]
        spec_diff = state.get("spec_diff")

        # def get_old_revision_blob(file_path: str):
        #     return context.git_helper.git_file_content_for_revision(
        #         file_path=file_path,
        #         revision_sha="0660516b7b1955e10a3e9e05bfc3da36c2988e9d"
        #     )

        # if spec_diff:
        #     old_models: str = get_old_revision_blob("web/models.py")
        #     old_entities_blob: str = get_old_revision_blob("entities.json")
        #     old_entities = json.loads(old_entities_blob)
        #     new_entities = state["entities"]

        #     generate_models_with_llm(project_path, old_models, old_entities, new_entities)
        #     return {}

        # else:
        project_name = state["project_name"]
        entities: list[Entity] = state["entities"]
        self.logger.info(f"Generating Django models in {project_path}")

        generate_models_from_template(project_path, project_name, to_entities(entities), "web")
        return {}
