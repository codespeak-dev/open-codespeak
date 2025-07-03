import os
import re
import json
import llm_cache
from typing import cast
from anthropic.types import ToolParam
from jinja2 import Environment, FileSystemLoader
from fileutils import load_template as load_template_jinja

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

TOOLS_DEFINITIONS: list[ToolParam] = [
    ToolParam(
        name="write_file",
        description="Write content to a new file",
        input_schema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to create"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file"
                }
            },
            "required": ["file_path", "content"]
        }
    )
]

def generate_models_with_llm(project_path: str, old_models: str, old_entities: list[dict], new_entities: list[dict]):
    client = llm_cache.Anthropic()

    system_prompt = """
    You are an expert Django developer.
    """

    user_prompt = load_template_jinja("prompts/generate_models_incremental.j2", old_models=old_models, old_entities=old_entities, new_entities=new_entities)

    message = client.messages.create(
        model="claude-3-7-sonnet-latest", 
        max_tokens=10000,
        temperature=0,
        system=system_prompt,
        tools=TOOLS_DEFINITIONS,
        messages=[{"role": "user", "content": user_prompt}]
    )

    tool_calls = [block for block in message.content if hasattr(block, 'type') and block.type == "tool_use"]
    if len(tool_calls) > 1:
        raise ValueError("Only one tool call is allowed, got: " + str(tool_calls))

    for tool_call in tool_calls:
        if tool_call.name == "write_file":
            tool_input = cast(dict, tool_call.input)
            if tool_input["file_path"] == "web/models.py":
                with open(os.path.join(project_path, "web/models.py"), "w", encoding="utf-8") as f:
                    f.write(tool_input["content"])
            else:
                raise ValueError(f"Only writing to web/models.py is supported, got: {tool_input['file_path']}")
        else:
            raise ValueError(f"Unknown tool: {tool_call.name}")

class GenerateModels(Phase):
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
        print(f"Generating Django models in {project_path}")

        generate_models_from_template(project_path, project_name, to_entities(entities), "web")
        return {}
