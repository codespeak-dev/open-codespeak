import os
import logging
from typing import cast
from anthropic.types import ToolParam
from colors import Colors
from phase_manager import State, Phase, Context
from with_step import with_step
from fileutils import load_template as load_template_jinja


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


def read_models_file(project_path: str) -> str:
    """Read the models.py file from the web app"""
    models_path = os.path.join(project_path, "web", "models.py")
    if not os.path.exists(models_path):
        raise FileNotFoundError(f"models.py not found at {models_path}")

    with open(models_path, 'r') as f:
        return f.read()


class GenerateDataModelTests(Phase):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__class__.__qualname__)
    description = "Generates data model tests for the Django project"

    def run(self, state: State, context: Context) -> dict:
        # Skip if entities are empty
        entities = state.get("entities", [])
        if not entities:
            self.logger.info(f"{Colors.BRIGHT_YELLOW}Skipping integration test generation - no entities found{Colors.END}")
            return {}

        project_path = state["project_path"]

        models_content = read_models_file(project_path)

        test_file_path = self.generate_data_model_tests(context, models_content, project_path)

        return {
            "data_model_test_path": test_file_path
        }

    def generate_data_model_tests(self, context: Context, models_content: str, project_path: str) -> str:
        """Use Claude to generate data model tests based on models.py"""

        system_prompt = "You are an expert Django developer."
        user_prompt = load_template_jinja("prompts/generate_data_model_tests.j2", models_content=models_content)

        with with_step("Generating data model tests..."):
            message = context.anthropic_client.create(
                model="claude-3-7-sonnet-latest",
                max_tokens=8192,
                temperature=0,
                system=system_prompt,
                tools=TOOLS_DEFINITIONS,
                messages=[{"role": "user", "content": user_prompt}]
            )

            tool_calls = [block for block in message.content if hasattr(block, 'type') and block.type == "tool_use"]
            if len(tool_calls) > 1:
                raise ValueError("Only one tool call is allowed, got: " + str(tool_calls))

            test_file_path = os.path.join(project_path, "web", "test_data_model.py")

            for tool_call in tool_calls:
                if tool_call.name == "write_file":
                    tool_input = cast(dict, tool_call.input)
                    if tool_input["file_path"] == "web/test_data_model.py":
                        with open(test_file_path, "w", encoding="utf-8") as f:
                            f.write(tool_input["content"])
                    else:
                        raise ValueError(f"Only writing to web/test_data_model.py is supported, got: {tool_input['file_path']}")
                else:
                    raise ValueError(f"Unknown tool: {tool_call.name}")

            return test_file_path

