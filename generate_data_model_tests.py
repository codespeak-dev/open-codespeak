import os
from typing import Optional
from colors import Colors
from phase_manager import State, Phase, Context
from with_step import with_streaming_step
import llm_cache


DATA_MODEL_TESTS_SYSTEM_PROMPT = """You are an expert Django developer. Given Django views.py content, generate a proper Django TestCase class that tests the Django models and their relationships. The test should:
1. Import from django.test import TestCase
2. Import the models from web.models
3. Import any other necessary Django modules (like datetime, uuid, etc.)
4. Inherit from django.test.TestCase (NOT unittest.TestCase)
5. Test model creation, relationships, and database integrity
6. Use self.assert* methods (like self.assertEqual, self.assertTrue, etc.)
7. Include proper test method names starting with 'test_'
8. Test foreign key relationships, cascade deletions, and unique constraints
9. Focus on testing the Django ORM and model layer, not API endpoints
10. Include a setUp method to create test data
11. Use from django.utils import timezone and timezone.now() instead of datetime.now() for datetime fields
Generate comprehensive tests that verify the models work correctly with the Django ORM.
IMPORTANT: Your response should be composed of only Python code with the complete Django TestCase class, no explanation or NO markdown formatting."""


def read_views_file(project_path: str) -> str:
    """Read the views.py file from the web app"""
    views_path = os.path.join(project_path, "web", "views.py")
    if not os.path.exists(views_path):
        raise FileNotFoundError(f"views.py not found at {views_path}")

    with open(views_path, 'r') as f:
        return f.read()


def generate_data_model_tests(views_content: str) -> str:
    """Use Claude to generate data model tests based on views.py"""
    client = llm_cache.Anthropic()

    with with_streaming_step("Generating data model tests with Claude...") as (input_tokens, output_tokens):
        response_text = ""
        # Count input tokens from system prompt and views content
        input_tokens[0] = len((DATA_MODEL_TESTS_SYSTEM_PROMPT + views_content).split())

        with client.messages.stream(
            model="claude-3-7-sonnet-latest",
            max_tokens=8192,
            temperature=0,
            system=DATA_MODEL_TESTS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": views_content}]
        ) as stream:
            for text in stream.text_stream:
                response_text += text
                output_tokens[0] += len(text.split())

    return response_text.strip()


def save_test_to_project(test_code: str, project_path: str) -> str:
    """Save the generated test code to the Django project's test directory"""
    test_file_path = os.path.join(project_path, "web", "test_data_model.py")

    with open(test_file_path, 'w') as f:
        f.write(test_code)

    return test_file_path


class GenerateDataModelTests(Phase):
    description = "Generates data model tests for the Django project"

    def run(self, state: State, context: Optional[Context] = None) -> dict:
        # Skip if entities are empty
        entities = state.get("entities", [])
        if not entities:
            print(f"{Colors.BRIGHT_YELLOW}Skipping integration test generation - no entities found{Colors.END}")
            return {}

        project_path = state["project_path"]

        views_content = read_views_file(project_path)

        test_code = generate_data_model_tests(views_content)
        test_file_path = save_test_to_project(test_code, project_path)

        return {
            "data_model_test_path": test_file_path
        }
