import os
import subprocess
import sys
import anthropic
import json
from typing import Dict, Any, Optional, List, Tuple
from colors import Colors
from state_machine import State, Transition
from with_step import with_step


ANALYSIS_SYSTEM_PROMPT = """You are an expert Python developer. Given integration test code and its error output, analyze whether the failure is due to a logical error (issue with the application logic/API itself) or a testing error (issue with the test code, wrong assumptions, bad test logic, etc.). Consider the conversation history to provide better analysis."""

FIX_TEST_SYSTEM_PROMPT = """You are an expert Python developer. Given integration test code, error output, and analysis, fix the test code to resolve the testing issues. Consider the conversation history to avoid repeating the same mistakes. Only return the corrected Python code, no explanation."""

FIX_LOGICAL_ERROR_SYSTEM_PROMPT = """You are an expert Django developer with access to tools to analyze and fix code. Given a Django project with logical errors revealed by integration tests, use the available tools to:
1. Read and analyze the project files (models.py, views.py, etc.)
2. Identify the root cause of the logical error
3. Make the necessary code changes to fix the issue
4. Ensure the fix is comprehensive and follows Django best practices
Use the tools methodically to understand the codebase before making changes."""


def run_integration_tests(test_code: str, project_path: str) -> Tuple[bool, str]:
    """Save test code to project and run it using unittest"""
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


def analyze_test_failure(test_code: str, error_output: str, message_history: List = None) -> Dict[str, Any]:
    """Use Claude to analyze test failure and determine if it's logical or testing issue"""
    client = anthropic.Anthropic()

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
        system=ANALYSIS_SYSTEM_PROMPT,
        messages=messages,
        tools=tools,
        tool_choice={"type": "tool", "name": "analyze_failure"}
    )

    return response.content[0].input


def fix_test_code(test_code: str, error_output: str, analysis: Dict[str, Any], message_history: List = None) -> str:
    """Use Claude to fix the test code based on error analysis"""
    client = anthropic.Anthropic()

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
        system=FIX_TEST_SYSTEM_PROMPT,
        messages=messages
    )

    return response.content[0].text.strip()


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


def fix_logical_error(project_path: str, test_code: str, error_output: str, analysis: Dict[str, Any], message_history: List = None) -> Tuple[bool, str]:
    """Use Claude with tools to fix logical errors in the Django project"""
    client = anthropic.Anthropic()

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
                system=FIX_LOGICAL_ERROR_SYSTEM_PROMPT,
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


class ReconcileIntegrationTests(Transition):
    def run(self, state: State) -> State:
        project_path = state["project_path"]
        test_code = state["integration_test_code"]

        # Initialize message history for the agent conversation
        message_history = []

        # Add initial context to message history
        message_history.append({
            "role": "user", 
            "content": f"I need to test this Django project and fix any issues found."
        })
        message_history.append({
            "role": "assistant", 
            "content": f"I've generated integration test code to verify the Django application."
        })

        max_retries = 8
        attempt = 0

        with with_step("Running integration tests and fixing issues..."):
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
                    break
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
                                raise Exception(f"Failed to fix logical error: {fix_message}")
                    else:
                        print(f"{Colors.BRIGHT_RED}Maximum retries exceeded - agent unable to resolve all issues{Colors.END}")
                        message_history.append({
                            "role": "assistant",
                            "content": "Reached maximum retry limit. Unable to resolve all issues automatically."
                        })
                        raise Exception("Maximum retries exceeded - unable to resolve all issues")

        return state.clone({
            "tests_passed": success,
            "final_test_code": test_code,
            "test_attempts": attempt
        })