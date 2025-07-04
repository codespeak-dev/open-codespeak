import os
import json
import logging
from colors import Colors
from phase_manager import State, Phase, Context
from with_step import with_step
from fileutils import load_prompt_template, LLMFileGenerator

SYSTEM_PROMPT = "You are an expert Django developer."
TEST_FILE_PATH = os.path.join("web", "test_data_model.py")

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
        spec_diff = state.get("spec_diff")

        def get_old_revision_blob(file_path: str):
            raise Exception("Incrementally generating data model tests is not supported yet")

            return context.git_helper.git_file_content_for_revision(
                file_path=file_path,
                revision_sha="948073984371d9f2a48c26c792da88fdecb0b50d"
            )

        if spec_diff:
            old_models: str = get_old_revision_blob("web/models.py")
            new_models: str = read_models_file(project_path)
            old_entities_blob: str = get_old_revision_blob("entities.json")
            old_entities = json.loads(old_entities_blob)
            new_entities = state["entities"]

            try:
                old_tests: str = get_old_revision_blob("web/test_data_model.py")
            except:
                old_tests = ""

            test_file_path = self.generate_data_model_tests_incremental(
                context, old_models, new_models, old_entities, new_entities, old_tests, project_path
            )
        else:
            models_content = read_models_file(project_path)
            test_file_path = self.generate_data_model_tests(context, models_content, project_path)

        return {
            "data_model_test_path": test_file_path
        }

    def generate_data_model_tests(self, context: Context, models_content: str, project_path: str) -> str:
        """Use Claude to generate data model tests based on models.py"""

        user_prompt = load_prompt_template("generate_data_model_tests", models_content=models_content)

        generator = LLMFileGenerator(max_tokens=8192)
        test_file_path = os.path.join(project_path, TEST_FILE_PATH)

        with with_step("Generating data model tests..."):
            return generator.generate_and_write(
                context.anthropic_client,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                expected_file_path=TEST_FILE_PATH,
                output_file_path=test_file_path
            )

    def generate_data_model_tests_incremental(self, context: Context, old_models: str, new_models: str, old_entities: list[dict], new_entities: list[dict], old_tests: str, project_path: str) -> str:
        """Use Claude to generate incremental data model tests based on changes"""

        user_prompt = load_prompt_template("generate_data_model_tests_incremental",
                                         old_models=old_models,
                                         new_models=new_models,
                                         old_entities=old_entities,
                                         new_entities=new_entities,
                                         old_tests=old_tests)

        generator = LLMFileGenerator(max_tokens=8192)
        test_file_path = os.path.join(project_path, TEST_FILE_PATH)

        with with_step("Generating incremental data model tests..."):
            return generator.generate_and_write(
                context.anthropic_client,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                expected_file_path=TEST_FILE_PATH,
                output_file_path=test_file_path
            )
