import os
import logging
from colors import Colors
from phase_manager import State, Phase, Context
from with_step import with_step
from fileutils import load_template as load_template_jinja, LLMFileGenerator




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
        
        generator = LLMFileGenerator(max_tokens=8192)
        test_file_path = os.path.join(project_path, "web", "test_data_model.py")

        with with_step("Generating data model tests..."):
            return generator.generate_and_write(
                context.anthropic_client,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                expected_file_path="web/test_data_model.py",
                output_file_path=test_file_path
            )

