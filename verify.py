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
        "IMPORTANT: Your response should be composed of only Python code with the complete Django TestCase class, no explanation or NO markdown formatting."
    )
    
    response = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=8192,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": views_content}]
    )
    
    return response.content[0].text.strip()

def fix_logical_error(project_path: str, test_code: str, error_output: str, analysis: Dict[str, Any], message_history: list = None) -> tuple[bool, str]:
    """Use Claude with tools to fix logical errors in the Django project"""
    client = anthropic.Anthropic()
    
    system_prompt = (
        "You are an expert Django developer with access to tools to analyze and fix code. "
        "Given a Django project with logical errors revealed by integration tests, use the available tools to:"
        "1. Read and analyze the project files (models.py, views.py, etc.)"
        "2. Identify the root cause of the logical error"
        "3. Make the necessary code changes to fix the issue"
        "4. Ensure the fix is comprehensive and follows Django best practices"
        "Use the tools methodically to understand the codebase before making changes."
    )
    
    tools = [
        {
            "name": "read_file",
            "description": "Read the contents of a file in the Django project",
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Relative path to file from project root"}
                },
                "required": ["file_path"]
            }
        },
        {
            "name": "write_file",
            "description": "Write or modify a file in the Django project",
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Relative path to file from project root"},
                    "content": {"type": "string", "description": "New file content"}
                },
                "required": ["file_path", "content"]
            }
        },
        {
            "name": "list_files",
            "description": "List files in a directory of the Django project",
            "input_schema": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Directory path relative to project root"}
                },
                "required": ["directory"]
            }
        }
    ]
    
    # Build messages from history
    messages = message_history.copy() if message_history else []
    messages.append({
        "role": "user", 
        "content": f"""I have a Django project with a logical error. Here's the context:

Test code that revealed the error:
{test_code}

Error output:
{error_output}

Analysis:
{json.dumps(analysis, indent=2)}

Project path: {project_path}

Please use the tools to analyze the project structure, identify the logical error, and fix it. Start by exploring the project structure and reading the key files."""
    })
    
    max_iterations = 10
    for iteration in range(max_iterations):
        try:
            response = client.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=8192,
                temperature=0,
                system=system_prompt,
                messages=messages,
                tools=tools
            )
            
            # Add assistant's response to conversation
            messages.append({"role": "assistant", "content": response.content})
            
            # Process tool calls
            if response.content and any(block.type == 'tool_use' for block in response.content):
                tool_results = []
                
                for block in response.content:
                    if block.type == 'tool_use':
                        tool_result = execute_tool(block.name, block.input, project_path)
                        tool_results.append({
                            "tool_use_id": block.id,
                            "content": tool_result
                        })
                
                # Add tool results to conversation
                messages.append({"role": "user", "content": tool_results})
                
            else:
                # No more tools needed, agent is done
                final_message = "".join([block.text for block in response.content if block.type == 'text'])
                return True, final_message
                
        except Exception as e:
            return False, f"Error during logical error fixing: {str(e)}"
    
    return False, "Maximum iterations reached while trying to fix logical error"

def execute_tool(tool_name: str, tool_input: Dict[str, Any], project_path: str) -> str:
    """Execute a tool call for the logical error fixing agent"""
    try:
        if tool_name == "read_file":
            file_path = os.path.join(project_path, tool_input["file_path"])
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    return f.read()
            else:
                return f"File not found: {tool_input['file_path']}"
                
        elif tool_name == "write_file":
            file_path = os.path.join(project_path, tool_input["file_path"])
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w') as f:
                f.write(tool_input["content"])
            return f"Successfully wrote to {tool_input['file_path']}"
            
        elif tool_name == "list_files":
            dir_path = os.path.join(project_path, tool_input["directory"])
            if os.path.exists(dir_path):
                files = os.listdir(dir_path)
                return "\n".join(files)
            else:
                return f"Directory not found: {tool_input['directory']}"
                
        else:
            return f"Unknown tool: {tool_name}"
            
    except Exception as e:
        return f"Tool execution error: {str(e)}"

def analyze_test_failure(test_code: str, error_output: str, message_history: list = None) -> Dict[str, Any]:
    """Use Claude to analyze test failure and determine if it's logical or testing issue"""
    client = anthropic.Anthropic()
    
    system_prompt = (
        "You are an expert Python developer. Given integration test code and its error output, "
        "analyze whether the failure is due to a logical error (issue with the application logic/API itself) "
        "or a testing error (issue with the test code, wrong assumptions, bad test logic, etc.). "
        "Consider the conversation history to provide better analysis."
    )
    
    # Build messages from history
    messages = message_history.copy() if message_history else []
    messages.append({"role": "user", "content": f"Test code:\n{test_code}\n\nError output:\n{error_output}"})
    
    tools = [{
        "name": "analyze_failure",
        "description": "Analyze test failure and provide categorization",
        "input_schema": {
            "type": "object",
            "properties": {
                "error_type": {
                    "type": "string",
                    "enum": ["logical_error", "testing_error"],
                    "description": "Whether the failure is due to application logic or test code issues"
                },
                "explanation": {
                    "type": "string",
                    "description": "Brief explanation of the issue"
                },
                "suggested_fix": {
                    "type": "string",
                    "description": "What should be done to fix it"
                }
            },
            "required": ["error_type", "explanation", "suggested_fix"]
        }
    }]
    
    response = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=8192,
        temperature=0,
        system=system_prompt,
        messages=messages,
        tools=tools,
        tool_choice={"type": "tool", "name": "analyze_failure"}
    )
    
    return response.content[0].input

def fix_test_code(test_code: str, error_output: str, analysis: Dict[str, Any], message_history: list = None) -> str:
    """Use Claude to fix the test code based on error analysis"""
    client = anthropic.Anthropic()
    
    system_prompt = (
        "You are an expert Python developer. Given integration test code, error output, and analysis, "
        "fix the test code to resolve the testing issues. "
        "Consider the conversation history to avoid repeating the same mistakes. "
        "Only return the corrected Python code, no explanation."
    )
    
    user_message = f"""Test code:
{test_code}

Error output:
{error_output}

Analysis:
{json.dumps(analysis, indent=2)}

Please fix the test code based on this information."""
    
    # Build messages from history
    messages = message_history.copy() if message_history else []
    messages.append({"role": "user", "content": user_message})
    
    response = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=2048,
        temperature=0,
        system=system_prompt,
        messages=messages
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
    """Run verification tests with agentic loop for both test and logical error fixing"""
    
    # Initialize message history for the agent conversation
    message_history = []
    
    views_content = read_views_file(project_path)

    # Generate integration tests
    print(f"\n{Colors.BRIGHT_CYAN}Generating integration tests...{Colors.END}")
    test_code = generate_integration_tests(views_content)
    print(f"Generated test code ({len(test_code)} chars)")
    
    # Add initial context to message history
    message_history.append({
        "role": "user", 
        "content": f"I need to test this Django views.py content and fix any issues found:\n{views_content[:500]}..."
    })
    message_history.append({
        "role": "assistant", 
        "content": f"I've generated integration test code to verify the Django application."
    })
    
    # Save test to project
    test_file_path = save_test_to_project(test_code, project_path)
    print(f"Saved test to: {Colors.BRIGHT_CYAN}{test_file_path}{Colors.END}")
    print(f"Test code preview:\n{Colors.BRIGHT_YELLOW}{test_code[:200]}...{Colors.END}")
    
    max_retries = 8  # Increased for agent loop with logical error fixing
    attempt = 0
    
    while attempt < max_retries:
        attempt += 1
        print(f"\n{Colors.BRIGHT_CYAN}Running integration tests (attempt {attempt}/{max_retries})...{Colors.END}")
        
        success, output = run_integration_tests(test_code, project_path)
        print(f"Test execution result: {'SUCCESS' if success else 'FAILED'}")
        print(f"Test output:\n{output[:300]}{'...' if len(output) > 300 else ''}")
        
        # Add test result to message history
        message_history.append({
            "role": "user",
            "content": f"Test attempt {attempt} result: {'SUCCESS' if success else 'FAILED'}\nOutput summary: {output[:200]}..."
        })
        
        if success:
            print(f"{Colors.BRIGHT_GREEN}All tests passed! Verification complete.{Colors.END}")
            message_history.append({
                "role": "assistant",
                "content": "Tests passed successfully! The Django application has been verified and any issues have been resolved."
            })
            return True
        else:
            print(f"{Colors.BRIGHT_RED}Tests failed on attempt {attempt}{Colors.END}")

            if attempt < max_retries:
                # Agent analysis with message history
                print(f"\n{Colors.BRIGHT_YELLOW}Agent analyzing failure...{Colors.END}")
                analysis = analyze_test_failure(test_code, output, message_history)

                print(f"Error type: {analysis['error_type']}")
                print(f"Explanation: {analysis['explanation']}")
                print(f"Suggested fix: {analysis['suggested_fix']}")
                
                # Add analysis to message history
                message_history.append({
                    "role": "assistant",
                    "content": f"Analysis: {analysis['error_type']} - {analysis['explanation']}. Suggested fix: {analysis['suggested_fix']}"
                })

                if analysis['error_type'] == 'testing_error':
                    print(f"\n{Colors.BRIGHT_YELLOW}Fixing test code...{Colors.END}")
                    old_test_code = test_code
                    test_code = fix_test_code(test_code, output, analysis, message_history)
                    
                    # Add fix to message history
                    message_history.append({
                        "role": "assistant",
                        "content": f"I've updated the test code to fix the testing error."
                    })
                    
                    print(f"Test code updated ({len(test_code)} chars)")
                    if test_code == old_test_code:
                        print(f"{Colors.BRIGHT_YELLOW}Warning: Test code unchanged, trying different approach{Colors.END}")
                        message_history.append({
                            "role": "user",
                            "content": "The test code wasn't changed. Please try a different approach to fix the testing error."
                        })
                        
                else:
                    print(f"{Colors.BRIGHT_YELLOW}Logical error detected - using agent to fix application code...{Colors.END}")
                    
                    # Add logical error context to message history
                    message_history.append({
                        "role": "user",
                        "content": f"Logical error detected in attempt {attempt}. Need to fix the application code."
                    })
                    
                    fix_success, fix_message = fix_logical_error(project_path, test_code, output, analysis, message_history)
                    
                    if fix_success:
                        print(f"{Colors.BRIGHT_GREEN}Agent successfully fixed logical error{Colors.END}")
                        print(f"Fix details: {fix_message[:200]}...")
                        
                        # Add successful fix to message history
                        message_history.append({
                            "role": "assistant",
                            "content": f"Successfully fixed logical error: {fix_message}"
                        })
                        
                        # Continue the loop to retest with the fixed code
                    else:
                        print(f"{Colors.BRIGHT_RED}Agent failed to fix logical error: {fix_message}{Colors.END}")
                        message_history.append({
                            "role": "assistant",
                            "content": f"Failed to fix logical error: {fix_message}"
                        })
                        return False
            else:
                print(f"{Colors.BRIGHT_RED}Maximum retries exceeded - agent unable to resolve all issues{Colors.END}")
                message_history.append({
                    "role": "assistant",
                    "content": "Reached maximum retry limit. Unable to resolve all issues automatically."
                })
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