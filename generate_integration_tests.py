import os
import subprocess
import sys
import anthropic
import json
from typing import Dict, Any, Optional
from colors import Colors
from state_machine import State, Transition
from with_step import with_step


INTEGRATION_TEST_SYSTEM_PROMPT = """You are an expert Django developer. Given Django views.py content, generate a proper Django TestCase class that tests the Django models and their relationships. The test should:
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


def generate_integration_tests(views_content: str) -> str:
    """Use Claude to generate integration tests based on views.py"""
    client = anthropic.Anthropic()
    
    response = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=8192,
        temperature=0,
        system=INTEGRATION_TEST_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": views_content}]
    )
    
    return response.content[0].text.strip()


def save_test_to_project(test_code: str, project_path: str) -> str:
    """Save the generated test code to the Django project's test directory"""
    test_file_path = os.path.join(project_path, "web", "test_integration.py")
    
    with open(test_file_path, 'w') as f:
        f.write(test_code)
    
    return test_file_path


class GenerateIntegrationTests(Transition):
    def run(self, state: State) -> State:
        project_path = state["project_path"]
        
        with with_step("Reading views.py file..."):
            views_content = read_views_file(project_path)
        
        with with_step("Generating integration tests with Claude..."):
            test_code = generate_integration_tests(views_content)
        
        with with_step("Saving integration tests to project..."):
            test_file_path = save_test_to_project(test_code, project_path)
            print(f"Saved test to: {Colors.BRIGHT_CYAN}{test_file_path}{Colors.END}")
        
        return state.clone({
            "integration_test_code": test_code,
            "integration_test_path": test_file_path
        })