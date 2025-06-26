import argparse
import os
import subprocess
import sys
import time
import anthropic
import json
import dotenv
import requests
import threading
from typing import Dict, Any, Optional
from contextlib import contextmanager

dotenv.load_dotenv()

# ANSI color codes
class Colors:
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'

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
    
    system_prompt = (
        "You are an expert Django developer. Given Django views.py content, generate a proper Django TestCase class "
        "that tests the Django models and their relationships. The test should:\n"
        "1. Import from django.test import TestCase\n"
        "2. Import the models from web.models\n"
        "3. Import any other necessary Django modules (like datetime, uuid, etc.)\n"
        "4. Inherit from django.test.TestCase (NOT unittest.TestCase)\n"
        "5. Test model creation, relationships, and database integrity\n"
        "6. Use self.assert* methods (like self.assertEqual, self.assertTrue, etc.)\n"
        "7. Include proper test method names starting with 'test_'\n"
        "8. Test foreign key relationships, cascade deletions, and unique constraints\n"
        "9. Focus on testing the Django ORM and model layer, not API endpoints\n"
        "10. Include a setUp method to create test data\n"
        "11. Use from django.utils import timezone and timezone.now() instead of datetime.now() for datetime fields\n"
        "Generate comprehensive tests that verify the models work correctly with the Django ORM.\n"
        "Your response should be composed of only Python code with the complete Django TestCase class, no explanation or markdown formatting."
    )
    
    user_message = f"Generate unittest integration test class for this Django views.py:\n\n{views_content}"
    
    response = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=8192,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )
    
    return response.content[0].text.strip()

def analyze_test_failure(test_code: str, error_output: str) -> Dict[str, Any]:
    """Use Claude to analyze test failure and determine if it's logical or testing issue"""
    client = anthropic.Anthropic()
    
    system_prompt = (
        "You are an expert Python developer. Given integration test code and its error output, "
        "analyze whether the failure is due to:\n"
        "1. 'logical_error' - Issue with the application logic/API itself\n"
        "2. 'testing_error' - Issue with the test code (wrong assumptions, bad test logic, etc.)\n\n"
        "Return a JSON object with:\n"
        "- 'error_type': 'logical_error' or 'testing_error'\n"
        "- 'explanation': Brief explanation of the issue\n"
        "- 'suggested_fix': What should be done to fix it\n"
        "Only return the JSON, no explanation."
    )
    
    user_message = f"Test code:\n{test_code}\n\nError output:\n{error_output}"
    
    response = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=8192,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )
    
    return json.loads(response.content[0].text.strip())

def fix_test_code(test_code: str, error_output: str, analysis: Dict[str, Any]) -> str:
    """Use Claude to fix the test code based on error analysis"""
    client = anthropic.Anthropic()
    
    system_prompt = (
        "You are an expert Python developer. Given integration test code, error output, and analysis, "
        "fix the test code to resolve the testing issues. "
        "Only return the corrected Python code, no explanation."
    )
    
    user_message = f"""Test code:
{test_code}

Error output:
{error_output}

Analysis:
{json.dumps(analysis, indent=2)}

Please fix the test code based on this information."""
    
    response = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=2048,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )
    
    return response.content[0].text.strip()

def save_test_to_project(test_code: str, project_path: str) -> str:
    """Save the generated test code to the Django project's test directory"""
    test_file_path = os.path.join(project_path, "web", "test_integration.py")
    
    with open(test_file_path, 'w') as f:
        f.write(test_code)
    
    return test_file_path

def run_integration_tests(test_code: str, project_path: str) -> tuple[bool, str]:
    """Save test code to project and run it using unittest"""
    # Save test to the project
    test_file_path = save_test_to_project(test_code, project_path)
    
    try:
        # Run the Django test using manage.py from the project directory
        result = subprocess.run(
            [sys.executable, 'manage.py', 'test', 'web.test_integration', '--verbosity=2'],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60
        )

        # Combine stdout and stderr for complete output
        output = result.stdout + result.stderr
        success = result.returncode == 0

        return success, output
        
    except subprocess.TimeoutExpired:
        return False, "Test execution timed out after 60 seconds"
    except Exception as e:
        return False, f"Exception during test execution: {str(e)}"

def run_verification_tests(project_path: str):
    """Run the actual verification tests with detailed output"""

    views_content = read_views_file(project_path)

    # Generate integration tests
    print(f"\n{Colors.BRIGHT_CYAN}Generating integration tests...{Colors.END}")
    test_code = generate_integration_tests(views_content)
    print(f"Generated test code ({len(test_code)} chars)")
    
    # Save test to project
    test_file_path = save_test_to_project(test_code, project_path)
    print(f"Saved test to: {Colors.BRIGHT_CYAN}{test_file_path}{Colors.END}")
    print(f"Test code preview:\n{Colors.BRIGHT_YELLOW}{test_code}...{Colors.END}")
    
    max_retries = 3
    for attempt in range(max_retries):
        print(f"\n{Colors.BRIGHT_CYAN}Running integration tests (attempt {attempt + 1}/{max_retries})...{Colors.END}")
        
        success, output = run_integration_tests(test_code, project_path)
        print(f"Test execution result: {'SUCCESS' if success else 'FAILED'}")
        print(f"Test output:\n{output}")
        
        if success:
            print(f"{Colors.BRIGHT_GREEN}All tests passed!{Colors.END}")
            return True
        else:
            print(f"{Colors.BRIGHT_RED}Tests failed{Colors.END}")

            if attempt < max_retries - 1:
                # Analyze failure
                print(f"\n{Colors.BRIGHT_YELLOW}Analyzing failure...{Colors.END}")
                analysis = analyze_test_failure(test_code, output)

                print(f"Error type: {analysis['error_type']}")
                print(f"Explanation: {analysis['explanation']}")
                print(f"Suggested fix: {analysis['suggested_fix']}")
                
                if analysis['error_type'] == 'testing_error':
                    print(f"\n{Colors.BRIGHT_YELLOW}Fixing test code...{Colors.END}")
                    test_code = fix_test_code(test_code, output, analysis)
                    print(f"Fixed test code:\n{Colors.BRIGHT_YELLOW}{test_code}{Colors.END}")
                else:
                    print(f"{Colors.BRIGHT_RED}Logical error detected in application{Colors.END}")
                    return False
            else:
                print(f"{Colors.BRIGHT_RED}Maximum retries exceeded{Colors.END}")
                return False
    
    return False

def main():
    parser = argparse.ArgumentParser(description="Verify Django project with integration tests")
    parser.add_argument('project_path', help='Path to the Django project directory')
    args = parser.parse_args()

    project_path = os.path.abspath(args.project_path)

    if not os.path.exists(project_path):
        print(f"{Colors.BRIGHT_RED}Error: Project directory not found: {project_path}{Colors.END}")
        sys.exit(1)

    print(f"Verifying project: {Colors.BOLD}{Colors.BRIGHT_CYAN}{project_path}{Colors.END}")

    success = run_verification_tests(project_path)
            
    if success:
        print(f"\n{Colors.BRIGHT_GREEN}Verification completed successfully!{Colors.END}")
    else:
        print(f"\n{Colors.BRIGHT_RED}Verification failed{Colors.END}")
        sys.exit(1)
    
if __name__ == "__main__":
    main()