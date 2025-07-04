from anthropic import APIStatusError
from anthropic.types import ToolParam
import os
import json
import difflib
import time
import random
import logging
from typing import cast
from colors import Colors
from google import genai
from google.genai import types as gemini_types
from phase_manager import Context
from tree_printer import tree_section, tree_info
from fileutils import format_file_content
from utils.logging_util import LoggingUtil

# Tool definitions constant for reuse
TOOLS_DEFINITIONS = [
    {
        "name": "list_files",
        "description": "List files in a directory",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the directory to list"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "read_file",
        "description": "Read contents of a file with optional offset and limit",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to read"
                },
                "offset": {
                    "type": "integer",
                    "description": "Optional: starting line number (1-based)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional: Maximum number of lines to read"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "edit_file",
        "description": "Perform exact string replacement in files with validation pipeline",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to edit"
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact string to replace (must exist in file)"
                },
                "new_string": {
                    "type": "string",
                    "description": "New string to replace with"
                },
                "expected_replacements": {
                    "type": "integer",
                    "description": "Expected number of replacements (default: 1)",
                    "default": 1
                }
            },
            "required": ["file_path", "old_string", "new_string"]
        }
    },
    {
        "name": "write_file",
        "description": "Write content to a new file",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to create"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file"
                }
            },
            "required": ["file_path", "content"]
        }
    }
]

# Tool-specific instructions for system prompt
ToolSpecificInstructions = {
    "edit_file": """CRITICAL:
- The old_string MUST NOT include line number prefixes from ReadFileTool
- Preserve exact indentation and whitespace
- Verify expected_replacements matches actual occurrences"""
}

def generate_tools_documentation(tools_definitions: list[dict]):
    """Generate tool documentation from TOOLS_DEFINITIONS"""
    docs = []
    for tool in tools_definitions:
        doc = f"### {tool['name']}\n{tool['description']}\n"

        # Add any tool-specific instructions
        if tool['name'] in ToolSpecificInstructions:
            doc += f"\n{ToolSpecificInstructions[tool['name']]}\n"

        doc += f"\nInput Schema:\n```json\n{json.dumps(tool['input_schema'], indent=2)}\n```\n"
        docs.append(doc)

    return "\n".join(docs)

IMPLEMENTATION_SYSTEM_PROMPT = f"""
You are a Django developer tasked with implementing work steps by creating Django views and HTML templates.

Your task is to implement each step by:
1. Analyzing the step's overall goal, key knowledge, and current plan
2. Creating appropriate Django view functions in views.py
3. Creating HTML template files in the templates directory
4. Adding URL patterns to urls.py if needed
5. Processing any screens or other work items within the step

For each step, parse the overall_goal, key_knowledge, current_plan, and any screens or other work items.
Create clean, functional Django code that follows best practices.
Do not remove any FastAPI related code.
Follow the same style and structure as the existing code.
When you are done, you do not need to summarize the work performed.
"""

def tools_prompt(tools_definitions: list[dict]):
    return f"""
            ## Available Tools

            You have access to the following tools:

            {generate_tools_documentation(tools_definitions)}

            ## Tool Usage Guidelines

            1. **Batching**: You can call multiple tools in a single response. When multiple independent pieces of information are requested, batch your tool calls together.

            2. **Read Before Write**: ALWAYS use read_file before edit_file or write_file.
            """


class ImplementationAgent:

    _system_prompt: str
    _tools_prompt: str
    _tools_definitions: list[dict]
    _check_read_before_write: bool

    def __init__(
        self,
        project_path: str,
        context: Context,
        provider: str | None = None,
        facts: str | None = None,
        system_prompt_override: str | None = None,
        tools_definitions_override: list[dict] | None = None,
        tools_prompt_override: str | None = None,
        check_read_before_write: bool = True,
    ):
        super().__init__()
        self.logger = logging.getLogger(__class__.__qualname__)
        self._system_prompt = system_prompt_override or IMPLEMENTATION_SYSTEM_PROMPT
        self._tools_prompt = tools_prompt_override or tools_prompt(tools_definitions_override or TOOLS_DEFINITIONS)
        self._tools_definitions = tools_definitions_override or TOOLS_DEFINITIONS
        self._check_read_before_write = check_read_before_write

        self.logger.info(f"{Colors.BRIGHT_BLUE}[AGENT INIT]{Colors.END} Creating ImplementationAgent")
        self.logger.info(f"  Project path: {project_path}")

        # Determine provider (env var or parameter)
        self.provider = provider or os.getenv('AI_PROVIDER', 'anthropic').lower()
        self.logger.info(f"  Provider: {self.provider}")

        self.project_path = project_path
        self.history = []
        self.file_state_cache = {}  # Track read files for validation
        self.always_yes = False  # Track if user chose "always yes"
        self.facts = facts

        # Initialize clients based on provider
        if self.provider == 'anthropic':
            self.anthropic_client = context.anthropic_client
            self.logger.info(f"  Anthropic client initialized")
        elif self.provider == 'gemini':
            # Initialize Gemini client
            api_key = os.getenv('GEMINI_API_KEY')
            if not api_key:
                raise ValueError("GEMINI_API_KEY environment variable required for Gemini")
            self.gemini_client = genai.Client(api_key=api_key)
            self.logger.info(f"  Gemini client initialized")
        else:
            raise ValueError(f"Unsupported provider: {self.provider}. Use 'anthropic' or 'gemini'")

        self.logger.info(f"{Colors.BRIGHT_BLUE}[AGENT INIT]{Colors.END} Agent initialized successfully")

    def truncate_for_debug(self, content: str, max_length: int = 500) -> str:
        """Truncate content for debugging output"""
        if isinstance(content, str) and len(content) > max_length:
            return content[:max_length] + f"... (truncated, total: {len(content)} chars)"
        return str(content)

    def get_tools_schema(self):
        """Get the tools schema for the current provider"""
        if self.provider == 'anthropic':
            return self.get_anthropic_tools_schema()
        elif self.provider == 'gemini':
            return self.get_gemini_tools_schema()
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def get_anthropic_tools_schema(self) -> list[ToolParam]:
        """Get the tools schema for the Anthropic API"""
        # Return only the schema fields needed for Anthropic API (exclude the 'prompt' field)
        return [
            ToolParam(
                name=tool["name"],
                description=tool["description"],
                input_schema=tool["input_schema"]
            )
            for tool in self._tools_definitions
        ]

    def get_gemini_tools_schema(self):
        """Get the tools schema for the Gemini API"""
        function_declarations = []

        for tool in self._tools_definitions:
            # Use custom description and schema for edit_file tool in Gemini
            if tool["name"] == "edit_file":
                # Custom Gemini-specific edit_file definition
                properties = {
                    "file_path": gemini_types.Schema(
                        type=gemini_types.Type.STRING,
                        description="Path to the file to edit"
                    ),
                    "old_string": gemini_types.Schema(
                        type=gemini_types.Type.STRING,
                        description="The exact literal text to replace, preferably unescaped. For single replacements (default), include at least 3 lines of context BEFORE and AFTER the target text, matching whitespace and indentation precisely. For multiple replacements, specify expected_replacements parameter. If this string is not the exact literal text (i.e. you escaped it) or does not match exactly, the tool will fail."
                    ),
                    "new_string": gemini_types.Schema(
                        type=gemini_types.Type.STRING,
                        description="The exact literal text to replace `old_string` with, preferably unescaped. Provide the EXACT text. Ensure the resulting code is correct and idiomatic."
                    ),
                    "expected_replacements": gemini_types.Schema(
                        type=gemini_types.Type.INTEGER,
                        description="Number of replacements expected. Defaults to 1 if not specified. Use when you want to replace multiple occurrences."
                    )
                }

                function_decl = gemini_types.FunctionDeclaration(
                    name="edit_file",
                    description="Replaces text within a file. By default, replaces a single occurrence, but can replace multiple occurrences when `expected_replacements` is specified. This tool requires providing significant context around the change to ensure precise targeting. Always use the read_file tool to examine the file's current content before attempting a text replacement.\n\nThe user has the ability to modify the `new_string` content. If modified, this will be stated in the response.\n\nExpectation for required parameters:\n1. `file_path` MUST be an absolute path; otherwise an error will be thrown.\n2. `old_string` MUST be the exact literal text to replace (including all whitespace, indentation, newlines, and surrounding code etc.).\n3. `new_string` MUST be the exact literal text to replace `old_string` with (also including all whitespace, indentation, newlines, and surrounding code etc.). Ensure the resulting code is correct and idiomatic.\n4. NEVER escape `old_string` or `new_string`, that would break the exact literal text requirement.\n**Important:** If ANY of the above are not satisfied, the tool will fail. CRITICAL for `old_string`: Must uniquely identify the single instance to change. Include at least 3 lines of context BEFORE and AFTER the target text, matching whitespace and indentation precisely. If this string matches multiple locations, or does not match exactly, the tool will fail.\n**Multiple replacements:** Set `expected_replacements` to the number of occurrences you want to replace. The tool will replace ALL occurrences that match `old_string` exactly. Ensure the number of replacements matches your expectation.",
                    parameters=gemini_types.Schema(
                        type=gemini_types.Type.OBJECT,
                        properties=properties,
                        required=["file_path", "old_string", "new_string"]
                    )
                )
            else:
                # Convert standard tool definition to Gemini format
                properties = {}
                required = tool["input_schema"].get("required", [])

                for prop_name, prop_def in tool["input_schema"]["properties"].items():
                    gemini_prop = gemini_types.Schema(
                        type=gemini_types.Type.STRING if prop_def["type"] == "string" else gemini_types.Type.INTEGER,
                        description=prop_def.get("description", "")
                    )
                    properties[prop_name] = gemini_prop

                function_decl = gemini_types.FunctionDeclaration(
                    name=tool["name"],
                    description=tool["description"],
                    parameters=gemini_types.Schema(
                        type=gemini_types.Type.OBJECT,
                        properties=properties,
                        required=required
                    )
                )

            function_declarations.append(function_decl)

        return [gemini_types.Tool(function_declarations=function_declarations)]

    # File patterns to ignore when listing directories
    IGNORED_PATTERNS = [
        '*.pyc',
        '*.pyo',
        '__pycache__',
        '.DS_Store',
        '*.txt',
        'codespeak_state.json',
        'spec.md',
        'spec.processed.md'
    ]

    def should_ignore_file(self, filename: str) -> bool:
        """Check if a file should be ignored based on ignore patterns"""
        import fnmatch
        for pattern in self.IGNORED_PATTERNS:
            if fnmatch.fnmatch(filename, pattern):
                return True
        return False

    def list_files(self, path: str):
        """List files in a directory with proper validation and formatting"""
        self.logger.info(f"{Colors.BRIGHT_YELLOW}[FILE OP]{Colors.END} Listing files in: {path}")

        full_path = os.path.join(self.project_path, path) if not os.path.isabs(path) else path
        try:
            if not os.path.exists(full_path):
                error_msg = f"Error: Directory not found or inaccessible: {path}"
                self.logger.info(f"{Colors.BRIGHT_RED}[FILE OP ERROR]{Colors.END} {error_msg}")
                self.history.append(error_msg)
                return {"success": False, "error": error_msg}

            if not os.path.isdir(full_path):
                error_msg = f"Error: Path is not a directory: {path}"
                self.logger.info(f"{Colors.BRIGHT_RED}[FILE OP ERROR]{Colors.END} {error_msg}")
                self.history.append(error_msg)
                return {"success": False, "error": error_msg}

            files = os.listdir(full_path)
            entries = []

            if len(files) == 0:
                result_msg = f"Directory {path} is empty."
                self.logger.info(f"{Colors.BRIGHT_GREEN}[FILE OP]{Colors.END} {result_msg}")
                self.history.append(f"Listed files in {path}: empty directory")
                return {"success": True, "result": result_msg}

            for file in files:
                if self.should_ignore_file(file):
                    continue

                file_full_path = os.path.join(full_path, file)
                
                try:
                    stats = os.stat(file_full_path)
                    is_dir = os.path.isdir(file_full_path)
                    entries.append({
                        'name': file,
                        'is_directory': is_dir,
                        # this will break caching, so if you need it take care of changing file sizes (e.g. logs)
                        # 'size': 0 if is_dir else stats.st_size,
                    })
                except Exception as e:
                    # Log error internally but don't fail the whole listing
                    self.logger.info(f"  Warning: Error accessing {file_full_path}: {e}")

            # Sort entries (directories first, then alphabetically)
            entries.sort(key=lambda x: (not x['is_directory'], x['name'].lower()))

            # Create formatted content for LLM
            directory_content = []
            for entry in entries:
                prefix = '[DIR] ' if entry['is_directory'] else ''
                directory_content.append(f"{prefix}{entry['name']}")

            result_message = f"Directory listing for {path}:\n" + '\n'.join(directory_content)
            display_message = f"Listed {len(entries)} item(s)."

            self.logger.info(f"{Colors.BRIGHT_GREEN}[FILE OP]{Colors.END} {display_message}")
            self.history.append(f"Listed files in {path}: {len(entries)} items")
            
            return {
                "success": True, 
                "result": result_message,
                "display": display_message,
                "entries": entries
            }

        except Exception as e:
            error_msg = f"Error listing directory: {str(e)}"
            self.logger.info(f"{Colors.BRIGHT_RED}[FILE OP ERROR]{Colors.END} {error_msg}")
            self.history.append(error_msg)
            return {"success": False, "error": error_msg}

    def read_file(self, file_path: str, offset: int | None = None, limit: int | None = None):
        """Read contents of a file with optional offset and limit"""
        full_path = os.path.join(self.project_path, file_path) if not os.path.isabs(file_path) else file_path

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Normalize line endings to LF for consistent processing (Gemini provider)
            if self.provider == 'gemini':
                content = content.replace('\r\n', '\n')

            # Store in cache for edit validation
            file_stats = os.stat(full_path)
            self.file_state_cache[file_path] = {
                'content': content,
                'timestamp': file_stats.st_mtime,
                'size': file_stats.st_size
            }

            # Format content using utility function
            display_content, metadata = format_file_content(content, offset, limit)

            # Create concise status message
            if offset is not None and limit is not None:
                status_msg = f"lines {offset}-{metadata.end_line}"
            elif offset is not None:
                status_msg = f"{metadata.lines_processed} lines from {offset}"
            elif limit is not None:
                status_msg = f"first {metadata.lines_processed} lines"
            else:
                status_msg = f"{metadata.lines_processed} lines"

            if metadata.truncated:
                status_msg += " [TRUNCATED]"

            tree_section(f"Read({file_path})", Colors.BRIGHT_GREEN)
            tree_info(f"Read {status_msg}")
            self.history.append(f"Read file: {file_path} ({metadata.lines_processed} lines)")
            return display_content

        except Exception as e:
            error_msg = f"Error reading file {file_path}: {str(e)}"
            self.logger.info(f"{Colors.BRIGHT_RED}[FILE OP ERROR]{Colors.END} {error_msg}")
            self.history.append(error_msg)
            return ""

    def count_occurrences(self, content: str, search_string: str) -> int:
        """Count occurrences of search_string in content"""
        return content.count(search_string)

    def generate_diff(self, old_content: str, new_content: str, file_path: str) -> str:
        """Generate a unified diff between old and new content"""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm=''
        )

        return ''.join(diff)

    def get_context_snippet(self, content: str, search_string: str, context_lines: int = 5) -> str:
        """Get a snippet showing the search_string with surrounding context"""
        lines = content.splitlines()

        # For multi-line search strings, search for the first non-empty line
        search_lines = search_string.splitlines()
        search_target = None
        for search_line in search_lines:
            search_line = search_line.strip()
            if search_line:  # Skip empty lines
                search_target = search_line
                break

        if not search_target:
            return "Context not found - empty search string"

        # Find the line containing the search_target
        target_line = -1
        for i, line in enumerate(lines):
            if search_target in line:
                target_line = i
                break

        if target_line == -1:
            return f"Context not found - '{search_target[:50]}...' not found in file"

        # Get context lines around the target
        start_line = max(0, target_line - context_lines)
        end_line = min(len(lines), target_line + context_lines + 1)

        snippet_lines = []
        for i in range(start_line, end_line):
            prefix = ">" if i == target_line else " "
            snippet_lines.append(f"{prefix} {i+1:4d}: {lines[i]}")

        return '\n'.join(snippet_lines)

    def write_file_simple(self, file_path: str, content: str) -> bool:
        """Write content to file"""
        full_path = os.path.join(self.project_path, file_path) if not os.path.isabs(file_path) else file_path

        try:
            dir_path = os.path.dirname(full_path)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)

            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            self.logger.info(f"  Error writing file: {e}")
            return False

    def edit_file(self, file_path: str, old_string: str, new_string: str, expected_replacements: int = 1):
        """Edit a file using exact string replacement with validation pipeline"""
        self.logger.info(f"{Colors.BRIGHT_YELLOW}[FILE EDIT]{Colors.END} Editing file: {file_path}")
        self.logger.info(f"  Old length: {len(old_string)}, New length: {len(new_string)}")
        self.logger.info(f"  Expected replacements: {expected_replacements}")

        # Validation 1: File must have been read first
        if self._check_read_before_write and file_path not in self.file_state_cache:
            error_msg = f"File must be read with read_file before editing: {file_path}"
            self.logger.info(f"{Colors.BRIGHT_RED}[EDIT ERROR]{Colors.END} {error_msg}")
            self.history.append(f"Edit failed: {error_msg}")
            return {"success": False, "error": error_msg}

        if not self._check_read_before_write:
            self.read_file(file_path) # load into cache if the agent not obliged to read before editing
        cached_file = self.file_state_cache[file_path]

        # Validation 2: Cannot edit empty files
        if not cached_file['content'] or cached_file['content'].strip() == "":
            error_msg = "Cannot edit empty file. Use WriteTool to add content."
            self.logger.info(f"{Colors.BRIGHT_RED}[EDIT ERROR]{Colors.END} {error_msg}")
            self.history.append(f"Edit failed: {error_msg}")
            return {"success": False, "error": error_msg}

        # Validation 3: No-op check
        if old_string == new_string:
            error_msg = "old_string and new_string cannot be identical"
            self.logger.info(f"{Colors.BRIGHT_RED}[EDIT ERROR]{Colors.END} {error_msg}")
            self.history.append(f"Edit failed: {error_msg}")
            return {"success": False, "error": error_msg}

        # Validation 4: Check occurrences
        content = cached_file['content']
        occurrences = self.count_occurrences(content, old_string)

        if occurrences == 0:
            error_msg = f"old_string not found in file: {file_path}"
            self.logger.info(f"{Colors.BRIGHT_RED}[EDIT ERROR]{Colors.END} {error_msg}")
            self.history.append(f"Edit failed: {error_msg}")
            return {"success": False, "error": error_msg}

        if occurrences != expected_replacements:
            error_msg = f"Expected {expected_replacements} replacements but found {occurrences}"
            self.logger.info(f"{Colors.BRIGHT_RED}[EDIT ERROR]{Colors.END} {error_msg}")
            self.history.append(f"Edit failed: {error_msg}")
            return {"success": False, "error": error_msg}

        # Perform replacement
        self.logger.info(f"{Colors.BRIGHT_CYAN}[EDIT]{Colors.END} Performing replacement...")
        new_content = content.replace(old_string, new_string, expected_replacements)

        # Generate diff
        diff = self.generate_diff(content, new_content, file_path)
        self.logger.info(f"{Colors.BRIGHT_CYAN}[EDIT]{Colors.END} Generated diff:")
        self.logger.info(diff)

        # Write file
        if not self.write_file_simple(file_path, new_content):
            error_msg = f"Failed to write file: {file_path}"
            self.logger.info(f"{Colors.BRIGHT_RED}[EDIT ERROR]{Colors.END} {error_msg}")
            self.history.append(f"Edit failed: {error_msg}")
            return {"success": False, "error": error_msg}

        # Update cache
        self.file_state_cache[file_path] = {
            'content': new_content,
            'timestamp': 0,
            'size': len(new_content)
        }

        # Generate context snippet
        snippet = self.get_context_snippet(new_content, new_string)

        self.logger.info(f"{Colors.BRIGHT_GREEN}[EDIT]{Colors.END} File successfully edited")
        self.logger.info(f"  Replacements made: {expected_replacements}")
        self.logger.info(f"  Context snippet:\n{snippet}")

        self.history.append(f"Edited file: {file_path} ({expected_replacements} replacements)")

        return {
            "success": True,
            "diff": diff,
            "snippet": snippet,
            "replacements": expected_replacements
        }

    def write_file(self, file_path: str, content: str):
        """Write content to a new file"""
        self.logger.info(f"{Colors.BRIGHT_YELLOW}[FILE OP]{Colors.END} Writing new file: {file_path}")
        self.logger.info(f"  Content length: {len(content)} characters, {len(content.splitlines())} lines")
        full_path = os.path.join(self.project_path, file_path) if not os.path.isabs(file_path) else file_path

        try:
            dir_path = os.path.dirname(full_path)
            if not os.path.exists(dir_path):
                self.logger.info(f"  Creating directory: {dir_path}")
                os.makedirs(dir_path, exist_ok=True)

            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.logger.info(f"{Colors.BRIGHT_GREEN}[FILE OP]{Colors.END} Successfully wrote file")
            self.history.append(f"Created file: {file_path}")
            return True
        except Exception as e:
            error_msg = f"Error writing file {file_path}: {str(e)}"
            self.logger.info(f"{Colors.BRIGHT_RED}[FILE OP ERROR]{Colors.END} {error_msg}")
            self.history.append(error_msg)
            return False

    def execute_tool_call(self, tool_name: str, tool_input: dict):
        """Execute a tool call and return the result"""
        # Skip confirmation if always_yes is set or DEBUG is not enabled
        debug_mode = os.getenv('DEBUG', '0') == '1'
        
        if self.always_yes or not debug_mode:
            # Silent execution for confirmed operations or when DEBUG is disabled
            pass
        else:
            # Ask for user confirmation only when DEBUG=1
            self.logger.info(f"{Colors.BRIGHT_YELLOW}[CONFIRMATION]{Colors.END} Do you want to execute this tool call?")
            self.logger.info(f"  Tool: {tool_name}")
            self.logger.info(f"  Parameters: {tool_input}")

            while True:
                response = input(f"{Colors.BRIGHT_CYAN}[INPUT]{Colors.END} Proceed? (y/n/a): ").lower().strip()
                if response in ['y', 'yes']:
                    break
                elif response in ['a', 'always']:
                    self.logger.info(f"{Colors.BRIGHT_GREEN}[ALWAYS YES]{Colors.END} Enabling always yes mode...")
                    self.always_yes = True
                    break
                elif response in ['n', 'no']:
                    self.logger.info(f"{Colors.BRIGHT_RED}[EXIT]{Colors.END} Exiting program...")
                    exit(0)
                else:
                    self.logger.info(f"{Colors.BRIGHT_RED}[INVALID]{Colors.END} Please enter 'y' (yes), 'n' (no/exit), or 'a' (always yes)")

        try:
            if tool_name == "list_files":
                result = self.list_files(tool_input["path"])
                return result
            elif tool_name == "read_file":
                offset = tool_input.get("offset")
                limit = tool_input.get("limit")
                result = self.read_file(tool_input["file_path"], offset, limit)
                return {"success": True, "result": result}
            elif tool_name == "edit_file":
                expected_replacements = tool_input.get("expected_replacements", 1)
                result = self.edit_file(
                    tool_input["file_path"],
                    tool_input["old_string"],
                    tool_input["new_string"],
                    expected_replacements
                )
                return result
            elif tool_name == "write_file":
                result = self.write_file(tool_input["file_path"], tool_input["content"])
                return {"success": True, "result": result}
            else:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_directory_tree(self, path: str, prefix: str = "", max_depth: int = 3, current_depth: int = 0):
        """Generate a directory tree structure"""
        if current_depth >= max_depth:
            return ""

        tree = ""
        try:
            items = sorted(os.listdir(path))
            filtered_items = []
            for item in items:
                if item.startswith('.') or self.should_ignore_file(item):
                    continue
                filtered_items.append(item)
            
            for i, item in enumerate(filtered_items):
                item_path = os.path.join(path, item)
                is_last = i == len(filtered_items) - 1

                if os.path.isdir(item_path):
                    tree += f"{prefix}{'└── ' if is_last else '├── '}{item}/\n"
                    extension = "    " if is_last else "│   "
                    tree += self.get_directory_tree(item_path, prefix + extension, max_depth, current_depth + 1)
                else:
                    tree += f"{prefix}{'└── ' if is_last else '├── '}{item}\n"
        except PermissionError:
            tree += f"{prefix}[Permission Denied]\n"
        except Exception as e:
            tree += f"{prefix}[Error: {str(e)}]\n"

        return tree

    def retry_with_backoff(self, func, max_retries=5, base_delay=1.0, max_delay=60.0):
        """Retry a function with exponential backoff for Anthropic API rate limiting/overload"""
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                if self.should_retry(e):
                    if attempt < max_retries - 1:  # Don't sleep on last attempt
                        # Calculate delay with exponential backoff and jitter
                        delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                        self.logger.info(f"{Colors.BRIGHT_YELLOW}[RETRY]{Colors.END} API overloaded (attempt {attempt + 1}/{max_retries}), retrying in {delay:.2f}s...")
                        time.sleep(delay)
                        continue
                # Re-raise non-retryable errors or if we've exhausted retries
                raise

        # If we get here, we've exhausted all retries
        raise Exception(f"Max retries ({max_retries}) exceeded for API call")

    def should_retry(self, e) -> bool:
        """Determine if an exception is retryable."""
        import httpx
        if isinstance(e, (httpx.ReadTimeout, httpx.ConnectTimeout)):
            return True
        if isinstance(e, APIStatusError):
            if hasattr(e, 'response') and hasattr(e.response, 'json'):
                error_type = e.response.json().get('error', {}).get('type', '')
            else:
                error_type = str(e)
            if 'overloaded' in error_type.lower() or 'rate_limit' in error_type.lower() or getattr(e, 'status_code', None) in [429, 529]:
                return True
        return False

    def run_streaming_conversation(self, system_prompt: str, messages: list) -> dict:
        """Run a conversation with the selected provider until completion"""
        if self.provider == 'anthropic':
            return self.run_anthropic_conversation(system_prompt, messages)
        elif self.provider == 'gemini':
            return self.run_gemini_conversation(messages)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def run_anthropic_conversation(self, system_prompt: str, messages: list) -> dict:
        """Run a streaming conversation with Claude until completion"""
        output_tokens = 0
        total_api_duration = 0.0

        # Continue conversation until no more tool calls
        iteration_count = 0
        while True:
            iteration_count += 1
            with LoggingUtil.Span(f"Conversation iteration #{iteration_count} ({len(messages)} messages)"):
                self.logger.info(f"{Colors.BRIGHT_MAGENTA}[AI REQUEST]{Colors.END} Sending request to Claude with {len(messages)} messages:")
                for i, message in enumerate(messages):
                    content_preview = self.truncate_for_debug(str(message['content']))
                    self.logger.info(f"  Message {i+1} ({message['role']}): {content_preview}")
                self.logger.info('')

                self.logger.info(f"{Colors.BRIGHT_MAGENTA}[AI STREAMING]{Colors.END} Starting streaming response...")

                # Track API call duration
                api_start_time = time.time()

                full_system_prompt = system_prompt + "\n" + self._tools_prompt

                # Use the streaming helper for cleaner code with retry logic
                def make_streaming_request():
                    with self.anthropic_client.stream(
                        model="claude-sonnet-4-20250514",
                        max_tokens=10000,
                        temperature=0,
                        system=full_system_prompt,
                        tools=self.get_anthropic_tools_schema(),
                        messages=messages
                    ) as stream:
                        self.logger.info(f"{Colors.BRIGHT_GREEN}[AI STREAMING]{Colors.END} Receiving response:")

                        # Stream text as it arrives
                        for text in stream.text_stream:
                            self.logger.info(f"{Colors.GREY}{text}{Colors.END}")

                        self.logger.info('')  # New line after streaming text

                        # Get the final message with all content blocks
                        return stream.get_final_message()

                with LoggingUtil.Span(f"Making streaming request"):
                    final_message = self.retry_with_backoff(make_streaming_request)

                api_end_time = time.time()
                api_call_duration = api_end_time - api_start_time
                total_api_duration += api_call_duration

                self.logger.info(f"{Colors.BRIGHT_MAGENTA}[AI RESPONSE]{Colors.END} Streaming completed")
                self.logger.info(f"  Output tokens: {final_message.usage.output_tokens}")
                self.logger.info(f"  API call duration: {api_call_duration:.2f}s")
                output_tokens += final_message.usage.output_tokens

                # Add assistant message to conversation
                messages.append({
                    "role": "assistant",
                    "content": final_message.content
                })

                # Check if there are tool calls to execute
                tool_calls = [block for block in final_message.content if hasattr(block, 'type') and block.type == "tool_use"]

                if not tool_calls:
                    self.logger.info(f"{Colors.BRIGHT_GREEN}[CONVERSATION]{Colors.END} No more tool calls, conversation complete")
                    break

                self.logger.info(f"{Colors.BRIGHT_CYAN}[TOOL EXECUTION]{Colors.END} Processing {len(tool_calls)} tool calls")

                # Execute tool calls and collect results
                tool_results = []
                for tool_call in tool_calls:
                    # Cast tool_call.input to dict for type safety
                    tool_input = cast(dict, tool_call.input)
                    span_name = f"Implementing \"{tool_call.name}\" tool call"
                    file_path = tool_input.get("path")
                    if file_path:
                        span_name = span_name + f", file: {file_path}"

                    with LoggingUtil.Span(span_name):
                        result = self.execute_tool_call(tool_call.name, tool_input)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_call.id,
                        "content": json.dumps(result)
                    })

                    # Only show errors or non-read operations in detail
                    if not result['success'] or tool_call.name != 'read_file':
                        result_preview = self.truncate_for_debug(json.dumps(result))
                        self.logger.info(f"{Colors.BRIGHT_GREEN if result['success'] else Colors.BRIGHT_RED}[TOOL RESULT]{Colors.END} {tool_call.name}: {'Success' if result['success'] else 'Error'}")
                        if not result['success']:
                            self.logger.info(f"  Result: {result_preview}")

                # Add tool results to conversation
                messages.append({
                    "role": "user",
                    "content": tool_results
                })

        return {
            "messages": messages,
            "total_output_tokens": output_tokens,
            "total_api_duration": total_api_duration
        }

    def run_gemini_conversation(self, messages: list) -> dict:
        """Run a conversation with Gemini until completion"""
        output_tokens = 0
        total_api_duration = 0.0
        gemini_contents = []

        # Convert messages to Gemini format
        for message in messages:
            if message['role'] == 'user':
                if isinstance(message['content'], str):
                    gemini_contents.append(gemini_types.Content(
                        role='user',
                        parts=[gemini_types.Part.from_text(text=message['content'])]
                    ))
                # Handle tool results
                elif isinstance(message['content'], list):
                    tool_parts = []
                    for content_item in message['content']:
                        if content_item.get('type') == 'tool_result':
                            tool_parts.append(gemini_types.Part.from_function_response(
                                name=content_item.get('tool_use_id', 'unknown'),
                                response=json.loads(content_item['content'])
                            ))
                    if tool_parts:
                        gemini_contents.append(gemini_types.Content(role='tool', parts=tool_parts))

        # Continue conversation until no more tool calls
        while True:
            self.logger.info(f"{Colors.BRIGHT_MAGENTA}[AI REQUEST]{Colors.END} Sending request to Gemini with {len(gemini_contents)} messages")

            try:
                # Track API call duration
                api_start_time = time.time()

                response = self.gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=gemini_contents,
                    config=gemini_types.GenerateContentConfig(
                        tools=self.get_gemini_tools_schema(),
                    ),
                )

                api_end_time = time.time()
                api_call_duration = api_end_time - api_start_time
                total_api_duration += api_call_duration

                self.logger.info(f"{Colors.BRIGHT_GREEN}[AI RESPONSE]{Colors.END} Gemini response received")
                self.logger.info(f"  API call duration: {api_call_duration:.2f}s")

                # Add assistant response to conversation
                if response.candidates and response.candidates[0].content:
                    gemini_contents.append(response.candidates[0].content)

                # Process response parts (text and function calls)
                function_calls = []
                text_parts = []

                if (response.candidates and 
                    response.candidates[0].content and 
                    response.candidates[0].content.parts):
                    for part in response.candidates[0].content.parts:
                        self.logger.info(f"Part: {part}")
                        if hasattr(part, 'function_call') and part.function_call:
                            function_calls.append(part)
                        elif hasattr(part, 'text') and part.text:
                            text_parts.append(part.text)

                # Print any text content
                if text_parts:
                    combined_text = ''.join(text_parts)
                    self.logger.info(f"{Colors.GREY}{combined_text}{Colors.END}")

                if not function_calls:
                    self.logger.info(f"{Colors.BRIGHT_GREEN}[CONVERSATION]{Colors.END} No more function calls, conversation complete")
                    break

                self.logger.info(f"{Colors.BRIGHT_CYAN}[TOOL EXECUTION]{Colors.END} Processing {len(function_calls)} function calls")

                # Execute function calls and collect results
                function_response_parts = []
                for function_call_part in function_calls:
                    function_call = function_call_part.function_call

                    # Extract function arguments
                    func_args = dict(function_call.args) if hasattr(function_call, 'args') and function_call.args else {}
                    result = self.execute_tool_call(function_call.name, func_args)

                    # Create function response - use the result directly
                    function_response = result

                    function_response_parts.append(gemini_types.Part.from_function_response(
                        name=function_call.name,
                        response=function_response
                    ))

                    # Only show errors or non-read operations in detail
                    if not result['success'] or function_call.name != 'read_file':
                        result_preview = self.truncate_for_debug(json.dumps(result))
                        self.logger.info(f"{Colors.BRIGHT_GREEN if result['success'] else Colors.BRIGHT_RED}[TOOL RESULT]{Colors.END} {function_call.name}: {'Success' if result['success'] else 'Error'}")
                        if not result['success']:
                            self.logger.info(f"  Result: {result_preview}")

                # Add function responses to conversation
                if function_response_parts:
                    gemini_contents.append(gemini_types.Content(role='tool', parts=function_response_parts))

            except Exception as e:
                self.logger.info(f"{Colors.BRIGHT_RED}[ERROR]{Colors.END} Gemini API error: {e}")
                break

        return {
            "messages": gemini_contents,
            "total_output_tokens": output_tokens,
            "total_api_duration": total_api_duration
        }

    def implement_step(self, step_text: str):
        """Implement a step by processing its components (goals, knowledge, plans, screens, etc.)"""
        self.logger.info(f"{Colors.BRIGHT_CYAN}[AGENT]{Colors.END} Starting step implementation")
        self.logger.info(f"  Step text length: {len(step_text)} characters")
        self.logger.info(f"  Step preview: {step_text[:100]}...")

        # Read current models and views for context
        self.logger.info(f"{Colors.BRIGHT_CYAN}[AGENT]{Colors.END} Gathering context files")
        models_content = self.read_file("web/models.py")
        views_content = self.read_file("web/views.py")
        urls_content = self.read_file("web/urls.py")

        # Get directory structure
        self.logger.info(f"{Colors.BRIGHT_CYAN}[AGENT]{Colors.END} Generating directory tree")
        directory_tree = self.get_directory_tree(self.project_path)
        self.logger.info(f"  Directory tree length: {len(directory_tree)} characters")

        # Create prompt for implementation
        prompt = f"""
<context name="project_structure">
{directory_tree}
</context>
<context name="general_facts">
{self.facts}
</context>
<context name="models" path="web/models.py">
{models_content}
</context>
<context name="urls" path="web/urls.py">
{urls_content}
</context>
<step>{step_text}</step>
"""

        self.logger.info(f"{Colors.BRIGHT_CYAN}[PROMPT]{Colors.END} Generated prompt:")
        self.logger.info(self.truncate_for_debug(prompt))
        self.logger.info(f"{Colors.BRIGHT_MAGENTA}[AI REQUEST]{Colors.END} Sending request to Claude with tools")

        # Initialize token tracking
        messages = [{"role": "user", "content": prompt}]
        input_tokens = len(prompt.split()) + len(self._system_prompt.split()) + len(self._tools_prompt.split())
        self.logger.info(f"{Colors.BRIGHT_MAGENTA}[AI REQUEST]{Colors.END} Estimated input tokens: {input_tokens}")

        # Run the streaming conversation
        with LoggingUtil.Span(f"Streaming conversation"):
            result = self.run_streaming_conversation(self._system_prompt, messages)

        self.logger.info(f"{Colors.BRIGHT_GREEN}[IMPLEMENTATION]{Colors.END} Step implementation completed")
        self.logger.info(f"  Total input tokens: {input_tokens}")
        self.logger.info(f"  Total output tokens: {result['total_output_tokens']}")
        self.logger.info(f"  Total API duration: {result.get('total_api_duration', 0):.2f}s")

        return result
