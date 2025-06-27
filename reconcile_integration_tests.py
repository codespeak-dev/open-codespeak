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


def read_current_test_code(test_file_path: str) -> str:
    """Read the current test code from the file"""
    try:
        with open(test_file_path, 'r') as f:
            return f.read()
    except Exception as e:
        return f"Error reading test file: {str(e)}"


def execute_tool(tool_name: str, tool_input: Dict[str, Any], project_path: str) -> str:
    """Execute a tool call for the issue fixing agent"""
    # Log tool call start
    print(f"{Colors.BRIGHT_YELLOW}🔧 TOOL CALL: {tool_name}{Colors.END}")
    print(f"   Input: {json.dumps(tool_input, indent=2)}")

    try:
        if tool_name == "read_file":
            file_path = os.path.join(project_path, tool_input["file_path"])
            print(f"   Reading file: {file_path}")
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    content = f.read()
                print(f"   ✅ Successfully read {len(content)} characters from {tool_input['file_path']}")
                return content
            else:
                error_msg = f"File not found: {tool_input['file_path']}"
                print(f"   ❌ {error_msg}")
                return error_msg

        elif tool_name == "write_file":
            file_path = os.path.join(project_path, tool_input["file_path"])
            content_length = len(tool_input["content"])
            print(f"   Writing {content_length} characters to: {file_path}")
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w') as f:
                f.write(tool_input["content"])
            success_msg = f"Successfully wrote to {tool_input['file_path']}"
            print(f"   ✅ {success_msg}")
            return success_msg

        elif tool_name == "list_files":
            dir_path = os.path.join(project_path, tool_input["directory"])
            print(f"   Listing files in: {dir_path}")
            if os.path.exists(dir_path):
                files = os.listdir(dir_path)
                print(f"   ✅ Found {len(files)} files in {tool_input['directory']}")
                return "\n".join(files)
            else:
                error_msg = f"Directory not found: {tool_input['directory']}"
                print(f"   ❌ {error_msg}")
                return error_msg

        else:
            error_msg = f"Unknown tool: {tool_name}"
            print(f"   ❌ {error_msg}")
            return error_msg

    except Exception as e:
        error_msg = f"Tool execution error: {str(e)}"
        print(f"   ❌ {error_msg}")
        return error_msg


def fix_issues(project_path: str, test_code: str, error_output: str, message_history: List = None) -> Tuple[bool, str, str]:
    """Use Claude with tools to fix issues revealed by integration tests"""
    print(f"\n{Colors.BRIGHT_YELLOW}🔍 Starting automated issue fixing process{Colors.END}")
    print(f"   Project path: {project_path}")
    print(f"   Test code length: {len(test_code)} characters")
    print(f"   Error output length: {len(error_output)} characters")
    print(f"   Message history length: {len(message_history) if message_history else 0} messages")

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
        print(f"\n{Colors.BRIGHT_YELLOW}🔄 Starting fix iteration {iteration + 1}/{max_iterations}{Colors.END}")

        try:
            print(f"   🧠 Calling Claude API with {len(messages)} messages...")
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=8192,
                temperature=0,
                system=FIX_ISSUES_SYSTEM_PROMPT,
                messages=messages,
                tools=tools
            )
            print(f"   ✅ Received response from Claude")

            # Add assistant's response to conversation
            messages.append({"role": "assistant", "content": response.content})

            # Process tool calls
            if response.content and any(block.type == 'tool_use' for block in response.content):
                tool_count = sum(1 for block in response.content if block.type == 'tool_use')
                print(f"\n{Colors.BRIGHT_MAGENTA}🤖 Claude is requesting {tool_count} tool call(s) on iteration {iteration + 1}{Colors.END}")

                tool_results = []

                for i, block in enumerate(response.content):
                    if block.type == 'tool_use':
                        print(f"\n{Colors.BRIGHT_CYAN}--- Tool Call {i + 1}/{tool_count} ---{Colors.END}")
                        print(f"Tool ID: {block.id}")

                        tool_result = execute_tool(block.name, block.input, project_path)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": tool_result
                        })

                        # Check if test code was updated
                        if block.name == "write_file" and block.input.get("file_path") == "web/test_integration.py":
                            updated_test_code = block.input.get("content", test_code)
                            print(f"   📝 Test code has been updated!")

                print(f"\n{Colors.BRIGHT_MAGENTA}✅ Completed all {tool_count} tool call(s){Colors.END}")

                # Add tool results to conversation
                messages.append({"role": "user", "content": tool_results})

            else:
                # No more tools needed, agent is done
                final_message = "".join([block.text for block in response.content if block.type == 'text'])
                print(f"\n{Colors.BRIGHT_GREEN}🎯 Claude completed analysis without requesting more tools{Colors.END}")
                print(f"   Final message: {final_message[:100]}{'...' if len(final_message) > 100 else ''}")
                return True, final_message, updated_test_code

        except Exception as e:
            error_msg = f"Error during issue fixing: {str(e)}"
            print(f"\n{Colors.BRIGHT_RED}❌ Exception in iteration {iteration + 1}: {error_msg}{Colors.END}")
            return False, error_msg, updated_test_code

    print(f"\n{Colors.BRIGHT_RED}⏰ Maximum iterations ({max_iterations}) reached while trying to fix issues{Colors.END}")
    return False, "Maximum iterations reached while trying to fix issues", updated_test_code


class ReconcileIntegrationTests(Transition):
    def run(self, state: State) -> State:
        project_path = state["project_path"]
        test_file_path = state["integration_test_path"]

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

                # Read the current test code from file to ensure we have the latest version
                test_code = read_current_test_code(test_file_path)

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
                        print(f"\n{Colors.BRIGHT_YELLOW}Analyzing and fixing issues...{Colors.END}")

                        fix_success, fix_message, updated_test_code = fix_issues(project_path, test_code, output, message_history)

                        if fix_success:
                            print(f"{Colors.BRIGHT_GREEN}Successfully applied fixes{Colors.END}")
                            print(f"Fix details: {fix_message[:200]}...")

                            # Add successful fix to message history
                            message_history.append({
                                "role": "assistant",
                                "content": f"Successfully applied fixes: {fix_message}"
                            })

                            # Continue the loop to retest with the fixes
                        else:
                            print(f"{Colors.BRIGHT_RED}Failed to fix issues: {fix_message}{Colors.END}")
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