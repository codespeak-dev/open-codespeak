import os
import subprocess
import sys
import json
import logging
from typing import Any
from colors import Colors
from phase_manager import State, Phase, Context
from with_step import with_step
from utils.logging_util import LoggingUtil

FIX_ISSUES_SYSTEM_PROMPT = """You are an expert Django developer with access to tools to analyze and fix code. Given a Django project with failing data model tests, use the available tools to:

1. Read and analyze the test code and error output
2. Determine whether the issue is with the test code itself or the application logic
3. Make the necessary code changes to resolve the issue - this could be:
   - Fixing the test code if it has incorrect assumptions or logic
   - Fixing the Django application code (models.py, views.py, etc.) if there are logical errors
   - Updating both if needed

Use the tools methodically to understand the codebase and make comprehensive fixes that follow Django best practices. Consider the conversation history to avoid repeating the same mistakes."""


def run_tests(test_file_path: str, project_path: str) -> tuple[bool, str]:
    """Run test using unittest"""

    if test_file_path.find(project_path) != 0:
        raise ValueError(f"Test file path {test_file_path} is not a child of project path {project_path}")
    test_file_relative_path = test_file_path.removeprefix(project_path)

    test_dotted_notation = test_file_relative_path.removeprefix("/").removesuffix(".py").replace("/", ".")

    try:
        # Run the Django test using manage.py from the project directory
        result = subprocess.run(
            [sys.executable, 'manage.py', 'test', test_dotted_notation, '--verbosity=2'],
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


def read_file(file_path: str) -> str:
    """Read the file"""
    try:
        with open(file_path, 'r') as f:
            return f.read()
    except Exception as e:
        return f"Error reading test file: {str(e)}"


def execute_tool(tool_name: str, tool_input: dict[str, Any], project_path: str) -> str:
    """Execute a tool call for the issue fixing agent"""
    logger = logging.getLogger("execute_tool")
    # Log tool call start
    logger.info(f"{Colors.BRIGHT_YELLOW}🔧 TOOL CALL: {tool_name}{Colors.END}")
    logger.info(f"   Input: {json.dumps(tool_input, indent=2)}")

    try:
        if tool_name == "read_file":
            file_path = os.path.join(project_path, tool_input["file_path"])
            logger.info(f"   Reading file: {file_path}")
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    content = f.read()
                logger.info(f"   ✅ Successfully read {len(content)} characters from {tool_input['file_path']}")
                return content
            else:
                error_msg = f"File not found: {tool_input['file_path']}"
                logger.info(f"   ❌ {error_msg}")
                return error_msg

        elif tool_name == "write_file":
            file_path = os.path.join(project_path, tool_input["file_path"])
            content_length = len(tool_input["content"])
            logger.info(f"   Writing {content_length} characters to: {file_path}")
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w') as f:
                f.write(tool_input["content"])
            success_msg = f"Successfully wrote to {tool_input['file_path']}"
            logger.info(f"   ✅ {success_msg}")
            return success_msg

        elif tool_name == "list_files":
            dir_path = os.path.join(project_path, tool_input["directory"])
            logger.info(f"   Listing files in: {dir_path}")
            if os.path.exists(dir_path):
                files = []
                for root, dirs, filenames in os.walk(dir_path):
                    # Get relative path from the requested directory
                    rel_root = os.path.relpath(root, dir_path)
                    if rel_root == ".":
                        rel_root = ""

                    # Add directories
                    for d in dirs:
                        if rel_root:
                            files.append(f"{rel_root}/{d}/")
                        else:
                            files.append(f"{d}/")

                    # Add files
                    for f in filenames:
                        if rel_root:
                            files.append(f"{rel_root}/{f}")
                        else:
                            files.append(f)

                files.sort()
                logger.info(f"   ✅ Found {len(files)} items in {tool_input['directory']} (recursive)")
                return "\n".join(files)
            else:
                error_msg = f"Directory not found: {tool_input['directory']}"
                logger.info(f"   ❌ {error_msg}")
                return error_msg

        elif tool_name == "makemigrations":
            logger.info(f"   Running Django makemigrations...")
            try:
                result = subprocess.run(
                    [sys.executable, 'manage.py', 'makemigrations', 'web'],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                output = result.stdout + result.stderr
                success = result.returncode == 0
                if success:
                    logger.info(f"   ✅ Makemigrations completed successfully")
                    return f"SUCCESS: Makemigrations completed successfully.\n\nOutput:\n{output}"
                else:
                    logger.info(f"   ❌ Makemigrations failed with code {result.returncode}")
                    return f"FAILED: Makemigrations failed with return code {result.returncode}.\n\nOutput:\n{output}"
            except Exception as e:
                error_msg = f"Error running makemigrations: {str(e)}"
                logger.info(f"   ❌ {error_msg}")
                return f"ERROR: {error_msg}"

        elif tool_name == "migrate":
            logger.info(f"   Running Django migrate...")
            try:
                result = subprocess.run(
                    [sys.executable, 'manage.py', 'migrate'],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                output = result.stdout + result.stderr
                success = result.returncode == 0
                if success:
                    logger.info(f"   ✅ Migration completed successfully")
                    return f"SUCCESS: Migration completed successfully.\n\nOutput:\n{output}"
                else:
                    logger.info(f"   ❌ Migration failed with code {result.returncode}")
                    return f"FAILED: Migration failed with return code {result.returncode}.\n\nOutput:\n{output}"
            except Exception as e:
                error_msg = f"Error running migrate: {str(e)}"
                logger.info(f"   ❌ {error_msg}")
                return f"ERROR: {error_msg}"

        else:
            error_msg = f"Unknown tool: {tool_name}"
            logger.info(f"   ❌ {error_msg}")
            return error_msg

    except Exception as e:
        error_msg = f"Tool execution error: {str(e)}"
        logger.info(f"   ❌ {error_msg}")
        return error_msg


def fix_issues(project_path: str, test_file_path: str, test_code: str, error_output: str, context: Context, message_history: list | None = None) -> tuple[bool, str, str]:
    """Use Claude with tools to fix issues revealed by integration tests"""
    logger = logging.getLogger("fix_issues")
    logger.info(f"\n{Colors.BRIGHT_YELLOW}🔍 Starting automated issue fixing process{Colors.END}")
    logger.info(f"   Project path: {project_path}")
    logger.info(f"   Test code length: {len(test_code)} characters")
    logger.info(f"   Error output length: {len(error_output)} characters")
    logger.info(f"   Message history length: {len(message_history) if message_history else 0} messages")

    if test_file_path.find(project_path) != 0:
        raise ValueError(f"Test file path {test_file_path} is not a child of project path {project_path}")
    test_file_relative_path = test_file_path.removeprefix(project_path).removeprefix("/")

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
        },
        {
            "name": "makemigrations",
            "description": "Run Django makemigrations for the web app",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "migrate",
            "description": "Run Django migrate to apply database migrations",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    ]

    # Build messages from history
    messages = message_history.copy() if message_history else []
    messages.append({
        "role": "user", 
        "content": f"""I have a Django project with failing data model tests. Here's the context:

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
        with LoggingUtil.Span(f"Test fix iteration {iteration + 1}/{max_iterations}"):
            logger.info(f"\n{Colors.BRIGHT_YELLOW}🔄 Starting fix iteration {iteration + 1}/{max_iterations}{Colors.END}")

            try:
                logger.info(f"   🧠 Calling Claude API with {len(messages)} messages...")
                response = context.anthropic_client.create(
                    model="claude-3-7-sonnet-latest",
                    max_tokens=8192,
                    temperature=0,
                    system=FIX_ISSUES_SYSTEM_PROMPT,
                    messages=messages,
                    tools=tools
                )
                logger.info(f"   ✅ Received response from Claude")

                # Add assistant's response to conversation
                messages.append({"role": "assistant", "content": response.content})

                # Process tool calls
                if response.content and any(block.type == 'tool_use' for block in response.content):
                    tool_count = sum(1 for block in response.content if block.type == 'tool_use')
                    logger.info(f"\n{Colors.BRIGHT_MAGENTA}🤖 Claude is requesting {tool_count} tool call(s) on iteration {iteration + 1}{Colors.END}")

                    tool_results = []

                    for i, block in enumerate(response.content):
                        if block.type == 'tool_use':
                            logger.info(f"\n{Colors.BRIGHT_CYAN}--- Tool Call {i + 1}/{tool_count} ---{Colors.END}")
                            logger.info(f"Tool ID: {block.id}")

                            tool_result = execute_tool(block.name, block.input, project_path)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": tool_result
                            })

                            # Check if test code was updated
                            if block.name == "write_file" and block.input.get("file_path") == test_file_relative_path:
                                updated_test_code = block.input.get("content", test_code)
                                logger.info(f"   📝 Test code has been updated!")

                    logger.info(f"\n{Colors.BRIGHT_MAGENTA}✅ Completed all {tool_count} tool call(s){Colors.END}")

                    # Add tool results to conversation
                    messages.append({"role": "user", "content": tool_results})

                else:
                    # No more tools needed, agent is done
                    final_message = "".join([block.text for block in response.content if block.type == 'text'])
                    logger.info(f"\n{Colors.BRIGHT_GREEN}🎯 Claude completed analysis without requesting more tools{Colors.END}")
                    logger.info(f"   Final message: {final_message[:100]}{'...' if len(final_message) > 100 else ''}")
                    return True, final_message, updated_test_code

            except Exception as e:
                error_msg = f"Error during issue fixing: {str(e)}"
                logger.info(f"\n{Colors.BRIGHT_RED}❌ Exception in iteration {iteration + 1}: {error_msg}{Colors.END}")

                import traceback
                traceback.print_exc()

                return False, error_msg, updated_test_code

    logger.info(f"\n{Colors.BRIGHT_RED}⏰ Maximum iterations ({max_iterations}) reached while trying to fix issues{Colors.END}")
    return False, "Maximum iterations reached while trying to fix issues", updated_test_code


class ReconcileDataModelTests(Phase):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__class__.__qualname__)

    description = "Fix failing data model tests"

    def run(self, state: State, context: Context) -> dict:
        entities = state.get("entities", [])
        if not entities:
            self.logger.info(f"{Colors.BRIGHT_YELLOW}Skipping integration test reconciliation - no entities found{Colors.END}")
            return {}

        project_path = state["project_path"]
        test_file_path = state["data_model_test_path"]

        # Initialize message history for the agent conversation
        message_history = []

        # Add initial context to message history
        message_history.append({
            "role": "user", 
            "content": f"I need to test this Django project and fix any issues found."
        })
        message_history.append({
            "role": "assistant", 
            "content": f"I'll run the data model tests and fix any issues that arise."
        })

        max_retries = 8
        attempt = 0

        with with_step("Running data model tests and fixing issues..."):
            while attempt < max_retries:
                attempt += 1
                with LoggingUtil.Span(f"Running data model tests (attempt {attempt}/{max_retries})"):
                    # self.logger.info(f"\n{Colors.BRIGHT_CYAN}Running data model tests (attempt {attempt}/{max_retries})...{Colors.END}")

                    # Read the current test code from file to ensure we have the latest version
                    test_code = read_file(test_file_path)

                    success, output = run_tests(test_file_path, project_path)
                    self.logger.info(f"Test execution result: {'SUCCESS' if success else 'FAILED'}")

                    if success:
                        self.logger.info(f"Test output:\n{output[:300]}{'...' if len(output) > 300 else ''}")
                    else:
                        self.logger.info(f"{Colors.BRIGHT_RED}Full test failure output:{Colors.END}")
                        self.logger.info(output)
                        self.logger.info(f"{Colors.BRIGHT_RED}--- End of test failure output ---{Colors.END}")

                    # Add test result to message history
                    message_history.append({
                        "role": "user",
                        "content": f"Test attempt {attempt} result: {'SUCCESS' if success else 'FAILED'}\nOutput: {output[:500]}..."
                    })

                    if success:
                        self.logger.info(f"{Colors.BRIGHT_GREEN}All tests passed! Verification complete.{Colors.END}")
                        message_history.append({
                            "role": "assistant",
                            "content": "Tests passed successfully! The Django application has been verified and any issues have been resolved."
                        })
                        break
                    else:
                        self.logger.info(f"{Colors.BRIGHT_RED}Tests failed on attempt {attempt}{Colors.END}")

                        if attempt < max_retries:
                            with LoggingUtil.Span(f"Analyzing and fixing issues"):
                                self.logger.info(f"\n{Colors.BRIGHT_YELLOW}Analyzing and fixing issues...{Colors.END}")

                                fix_success, fix_message, updated_test_code = fix_issues(project_path, test_file_path, test_code, output, context, message_history)

                                if fix_success:
                                    self.logger.info(f"{Colors.BRIGHT_GREEN}Successfully applied fixes{Colors.END}")
                                    self.logger.info(f"Fix details: {fix_message[:200]}...")

                                    # Add successful fix to message history
                                    message_history.append({
                                        "role": "assistant",
                                        "content": f"Successfully applied fixes: {fix_message}"
                                    })

                                    # Continue the loop to retest with the fixes
                                else:
                                    self.logger.info(f"{Colors.BRIGHT_RED}Failed to fix issues: {fix_message}{Colors.END}")
                                    message_history.append({
                                        "role": "assistant",
                                        "content": f"Failed to fix issues: {fix_message}"
                                    })
                                    raise Exception(f"Failed to fix issues: {fix_message}")
                        else:
                            self.logger.info(f"{Colors.BRIGHT_RED}Maximum retries exceeded - unable to resolve all issues{Colors.END}")
                            message_history.append({
                                "role": "assistant",
                                "content": "Reached maximum retry limit. Unable to resolve all issues automatically."
                            })
                            raise Exception("Maximum retries exceeded - unable to resolve all issues")

        return {}