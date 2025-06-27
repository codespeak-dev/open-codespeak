import os
import subprocess
import sys
import anthropic
import json
from typing import Dict, Any, Optional, List, Tuple
from colors import Colors
from state_machine import State, Transition
from with_step import with_step


FIX_ISSUES_SYSTEM_PROMPT = """You are an expert Django developer with access to tools to analyze and fix code. Given a Django project with failing integration tests, use the available tools to:

1. Read and analyze the test code and error output
2. Determine whether the issue is with the test code itself or the application logic
3. Make the necessary code changes to resolve the issue - this could be:
   - Fixing the test code if it has incorrect assumptions or logic
   - Fixing the Django application code (models.py, views.py, etc.) if there are logical errors
   - Updating both if needed

Use the tools methodically to understand the codebase and make comprehensive fixes that follow Django best practices. Consider the conversation history to avoid repeating the same mistakes."""


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


def execute_tool(tool_name: str, tool_input: Dict[str, Any], project_path: str) -> str:
    """Execute a tool call for the issue fixing agent"""
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


def fix_issues(project_path: str, test_code: str, error_output: str, message_history: List = None) -> Tuple[bool, str, str]:
    """Use Claude with tools to fix issues revealed by integration tests"""
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
        "content": f"""I have a Django project with failing integration tests. Here's the context:

Test code:
{test_code}

Error output:
{error_output}

Project path: {project_path}

Please use the tools to analyze the project structure, identify what's causing the test failure, and fix it. This could involve fixing the test code if it has issues, or fixing the Django application code if there are logical errors. Start by exploring the project structure and reading the key files."""
    })

    max_iterations = 10
    updated_test_code = test_code

    for iteration in range(max_iterations):
        try:
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=8192,
                temperature=0,
                system=FIX_ISSUES_SYSTEM_PROMPT,
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
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": tool_result
                        })

                        # Check if test code was updated
                        if block.name == "write_file" and block.input.get("file_path") == "web/test_integration.py":
                            updated_test_code = block.input.get("content", test_code)

                # Add tool results to conversation
                messages.append({"role": "user", "content": tool_results})

            else:
                # No more tools needed, agent is done
                final_message = "".join([block.text for block in response.content if block.type == 'text'])
                return True, final_message, updated_test_code

        except Exception as e:
            return False, f"Error during issue fixing: {str(e)}", updated_test_code

    return False, "Maximum iterations reached while trying to fix issues", updated_test_code


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
            "content": f"I'll run the integration tests and fix any issues that arise."
        })

        max_retries = 8
        attempt = 0

        with with_step("Running integration tests and fixing issues..."):
            while attempt < max_retries:
                attempt += 1
                print(f"\n{Colors.BRIGHT_CYAN}Running integration tests (attempt {attempt}/{max_retries})...{Colors.END}")

                success, output = run_integration_tests(test_code, project_path)
                print(f"Test execution result: {'SUCCESS' if success else 'FAILED'}")

                if success:
                    print(f"Test output:\n{output[:300]}{'...' if len(output) > 300 else ''}")
                else:
                    print(f"{Colors.BRIGHT_RED}Full test failure output:{Colors.END}")
                    print(output)
                    print(f"{Colors.BRIGHT_RED}--- End of test failure output ---{Colors.END}")

                # Add test result to message history
                message_history.append({
                    "role": "user",
                    "content": f"Test attempt {attempt} result: {'SUCCESS' if success else 'FAILED'}\nOutput: {output[:500]}..."
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
                        print(f"\n{Colors.BRIGHT_YELLOW}AI agent analyzing and fixing issues...{Colors.END}")

                        fix_success, fix_message, updated_test_code = fix_issues(project_path, test_code, output, message_history)

                        if fix_success:
                            print(f"{Colors.BRIGHT_GREEN}AI agent successfully applied fixes{Colors.END}")
                            print(f"Fix details: {fix_message[:200]}...")

                            # Update test code if it was modified
                            test_code = updated_test_code

                            # Add successful fix to message history
                            message_history.append({
                                "role": "assistant",
                                "content": f"Successfully applied fixes: {fix_message}"
                            })

                            # Continue the loop to retest with the fixes
                        else:
                            print(f"{Colors.BRIGHT_RED}AI agent failed to fix issues: {fix_message}{Colors.END}")
                            message_history.append({
                                "role": "assistant",
                                "content": f"Failed to fix issues: {fix_message}"
                            })
                            raise Exception(f"Failed to fix issues: {fix_message}")
                    else:
                        print(f"{Colors.BRIGHT_RED}Maximum retries exceeded - unable to resolve all issues{Colors.END}")
                        message_history.append({
                            "role": "assistant",
                            "content": "Reached maximum retry limit. Unable to resolve all issues automatically."
                        })
                        raise Exception("Maximum retries exceeded - unable to resolve all issues")

        return state.clone()