import anthropic
import os
import re
import json
import difflib
from colors import Colors
from phase_manager import State, Phase, Context

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
                    "description": "Starting line number (1-based, default: 1)",
                    "default": 1
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read (default: 1000)",
                    "default": 1000
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

def generate_tools_documentation():
    """Generate tool documentation from TOOLS_DEFINITIONS"""
    docs = []
    for tool in TOOLS_DEFINITIONS:
        doc = f"### {tool['name']}\n{tool['description']}\n"

        # Add any tool-specific instructions
        if tool['name'] in ToolSpecificInstructions:
            doc += f"\n{ToolSpecificInstructions[tool['name']]}\n"

        doc += f"\nInput Schema:\n```json\n{json.dumps(tool['input_schema'], indent=2)}\n```\n"
        docs.append(doc)

    return "\n".join(docs)

IMPLEMENTATION_SYSTEM_PROMPT = f"""
You are a Django developer tasked with implementing a screen by creating Django views and HTML templates.

Your task is to implement each screen by:
1. Creating appropriate Django view functions in views.py
2. Creating HTML template files in the templates directory
3. Adding URL patterns to urls.py if needed

For each screen, parse the name, URL pattern, description and actions.
Create clean, functional Django code that follows best practices.

Always use the available tools to read existing files, create new files, and edit existing files.

## Available Tools

You have access to the following tools:

{generate_tools_documentation()}

## Tool Usage Guidelines

1. **Batching**: You can call multiple tools in a single response. When multiple independent pieces of information are requested, batch your tool calls together.

2. **Read Before Write**: ALWAYS use read_file before edit_file or write_file.
"""

class ImplementationAgent:
    def __init__(self, project_path: str):
        print(f"{Colors.BRIGHT_BLUE}[AGENT INIT]{Colors.END} Creating ImplementationAgent")
        print(f"  Project path: {project_path}")
        self.project_path = project_path
        self.history = []
        self.client = anthropic.Anthropic()
        self.file_state_cache = {}  # Track read files for validation
        self.always_yes = False  # Track if user chose "always yes"
        print(f"{Colors.BRIGHT_BLUE}[AGENT INIT]{Colors.END} Agent initialized successfully")

    def truncate_for_debug(self, content: str, max_length: int = 500) -> str:
        """Truncate content for debugging output"""
        if isinstance(content, str) and len(content) > max_length:
            return content[:max_length] + f"... (truncated, total: {len(content)} chars)"
        return str(content)

    def get_tools_schema(self):
        """Get the tools schema for the Anthropic API"""
        # Return only the schema fields needed for Anthropic API (exclude the 'prompt' field)
        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"]
            }
            for tool in TOOLS_DEFINITIONS
        ]

    def list_files(self, path: str):
        """List files in a directory"""
        print(f"{Colors.BRIGHT_YELLOW}[FILE OP]{Colors.END} Listing files in: {path}")
        full_path = os.path.join(self.project_path, path) if not os.path.isabs(path) else path
        print(f"  Full path: {full_path}")

        try:
            files = os.listdir(full_path)
            print(f"{Colors.BRIGHT_GREEN}[FILE OP]{Colors.END} Found {len(files)} files: {files}")
            self.history.append(f"Listed files in {path}: {files}")
            return files
        except Exception as e:
            error_msg = f"Error listing files in {path}: {str(e)}"
            print(f"{Colors.BRIGHT_RED}[FILE OP ERROR]{Colors.END} {error_msg}")
            self.history.append(error_msg)
            return []

    def read_file(self, file_path: str, offset: int = 1, limit: int = 1000):
        """Read contents of a file with optional offset and limit"""
        print(f"{Colors.BRIGHT_YELLOW}[FILE OP]{Colors.END} Reading file: {file_path}")
        print(f"  Offset: {offset}, Limit: {limit}")
        full_path = os.path.join(self.project_path, file_path) if not os.path.isabs(file_path) else file_path
        print(f"  Full path: {full_path}")

        try:
            lines = []
            line_number = 0
            truncated = False

            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Store in cache for edit validation
            file_stats = os.stat(full_path)
            self.file_state_cache[file_path] = {
                'content': content,
                'timestamp': file_stats.st_mtime,
                'size': file_stats.st_size
            }

            # Process lines for display
            for line in content.splitlines():
                line_number += 1

                # Skip lines before offset
                if line_number < offset:
                    continue

                # Check if we've reached the limit
                if len(lines) >= limit:
                    truncated = True
                    break

                # Truncate long lines
                line_content = line
                if len(line_content) > 2000:
                    line_content = line_content[:2000] + '... (truncated)'

                # Format with line numbers (cat -n style)
                formatted_line = f"{line_number}\t{line_content}"
                lines.append(formatted_line)

            display_content = '\n'.join(lines)
            status_msg = f"Read {len(lines)} lines (line {offset}-{offset + len(lines) - 1})"
            if truncated:
                status_msg += " [TRUNCATED]"

            print(f"{Colors.BRIGHT_GREEN}[FILE OP]{Colors.END} {status_msg}")
            self.history.append(f"Read file: {file_path} ({status_msg})")
            return display_content

        except Exception as e:
            error_msg = f"Error reading file {file_path}: {str(e)}"
            print(f"{Colors.BRIGHT_RED}[FILE OP ERROR]{Colors.END} {error_msg}")
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
            print(f"  Error writing file: {e}")
            return False

    def edit_file(self, file_path: str, old_string: str, new_string: str, expected_replacements: int = 1):
        """Edit a file using exact string replacement with validation pipeline"""
        print(f"{Colors.BRIGHT_YELLOW}[FILE EDIT]{Colors.END} Editing file: {file_path}")
        print(f"  Old length: {len(old_string)}, New length: {len(new_string)}")
        print(f"  Expected replacements: {expected_replacements}")

        # Validation 1: File must have been read first
        if file_path not in self.file_state_cache:
            error_msg = f"File must be read with read_file before editing: {file_path}"
            print(f"{Colors.BRIGHT_RED}[EDIT ERROR]{Colors.END} {error_msg}")
            self.history.append(f"Edit failed: {error_msg}")
            return {"success": False, "error": error_msg}

        cached_file = self.file_state_cache[file_path]

        # Validation 2: Cannot edit empty files
        if not cached_file['content'] or cached_file['content'].strip() == "":
            error_msg = "Cannot edit empty file. Use WriteTool to add content."
            print(f"{Colors.BRIGHT_RED}[EDIT ERROR]{Colors.END} {error_msg}")
            self.history.append(f"Edit failed: {error_msg}")
            return {"success": False, "error": error_msg}

        # Validation 3: No-op check
        if old_string == new_string:
            error_msg = "old_string and new_string cannot be identical"
            print(f"{Colors.BRIGHT_RED}[EDIT ERROR]{Colors.END} {error_msg}")
            self.history.append(f"Edit failed: {error_msg}")
            return {"success": False, "error": error_msg}

        # Validation 4: Check occurrences
        content = cached_file['content']
        occurrences = self.count_occurrences(content, old_string)

        if occurrences == 0:
            error_msg = f"old_string not found in file: {file_path}"
            print(f"{Colors.BRIGHT_RED}[EDIT ERROR]{Colors.END} {error_msg}")
            self.history.append(f"Edit failed: {error_msg}")
            return {"success": False, "error": error_msg}

        if occurrences != expected_replacements:
            error_msg = f"Expected {expected_replacements} replacements but found {occurrences}"
            print(f"{Colors.BRIGHT_RED}[EDIT ERROR]{Colors.END} {error_msg}")
            self.history.append(f"Edit failed: {error_msg}")
            return {"success": False, "error": error_msg}

        # Perform replacement
        print(f"{Colors.BRIGHT_CYAN}[EDIT]{Colors.END} Performing replacement...")
        new_content = content.replace(old_string, new_string, expected_replacements)

        # Generate diff
        diff = self.generate_diff(content, new_content, file_path)
        print(f"{Colors.BRIGHT_CYAN}[EDIT]{Colors.END} Generated diff:")
        print(diff)

        # Write file
        if not self.write_file_simple(file_path, new_content):
            error_msg = f"Failed to write file: {file_path}"
            print(f"{Colors.BRIGHT_RED}[EDIT ERROR]{Colors.END} {error_msg}")
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

        print(f"{Colors.BRIGHT_GREEN}[EDIT]{Colors.END} File successfully edited")
        print(f"  Replacements made: {expected_replacements}")
        print(f"  Context snippet:\n{snippet}")

        self.history.append(f"Edited file: {file_path} ({expected_replacements} replacements)")

        return {
            "success": True,
            "diff": diff,
            "snippet": snippet,
            "replacements": expected_replacements
        }

    def write_file(self, file_path: str, content: str):
        """Write content to a new file"""
        print(f"{Colors.BRIGHT_YELLOW}[FILE OP]{Colors.END} Writing new file: {file_path}")
        print(f"  Content length: {len(content)} characters, {len(content.splitlines())} lines")
        full_path = os.path.join(self.project_path, file_path) if not os.path.isabs(file_path) else file_path

        try:
            dir_path = os.path.dirname(full_path)
            if not os.path.exists(dir_path):
                print(f"  Creating directory: {dir_path}")
                os.makedirs(dir_path, exist_ok=True)

            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"{Colors.BRIGHT_GREEN}[FILE OP]{Colors.END} Successfully wrote file")
            self.history.append(f"Created file: {file_path}")
            return True
        except Exception as e:
            error_msg = f"Error writing file {file_path}: {str(e)}"
            print(f"{Colors.BRIGHT_RED}[FILE OP ERROR]{Colors.END} {error_msg}")
            self.history.append(error_msg)
            return False

    def execute_tool_call(self, tool_name: str, tool_input: dict):
        """Execute a tool call and return the result"""
        print(f"{Colors.BRIGHT_CYAN}[TOOL CALL]{Colors.END} Requesting to execute: {tool_name}")
        print(f"  Input: {tool_input}")

        # Skip confirmation if always_yes is set
        if self.always_yes:
            print(f"{Colors.BRIGHT_GREEN}[AUTO-CONFIRMED]{Colors.END} Executing tool (always yes mode)...")
        else:
            # Ask for user confirmation
            print(f"{Colors.BRIGHT_YELLOW}[CONFIRMATION]{Colors.END} Do you want to execute this tool call?")
            print(f"  Tool: {tool_name}")
            print(f"  Parameters: {tool_input}")

            while True:
                response = input(f"{Colors.BRIGHT_CYAN}[INPUT]{Colors.END} Proceed? (y/n/a): ").lower().strip()
                if response in ['y', 'yes']:
                    print(f"{Colors.BRIGHT_GREEN}[CONFIRMED]{Colors.END} Executing tool...")
                    break
                elif response in ['a', 'always']:
                    print(f"{Colors.BRIGHT_GREEN}[ALWAYS YES]{Colors.END} Executing tool and enabling always yes mode...")
                    self.always_yes = True
                    break
                elif response in ['n', 'no']:
                    print(f"{Colors.BRIGHT_RED}[EXIT]{Colors.END} Exiting program...")
                    exit(0)
                else:
                    print(f"{Colors.BRIGHT_RED}[INVALID]{Colors.END} Please enter 'y' (yes), 'n' (no/exit), or 'a' (always yes)")

        try:
            if tool_name == "list_files":
                result = self.list_files(tool_input["path"])
                return {"success": True, "result": result}
            elif tool_name == "read_file":
                offset = tool_input.get("offset", 1)
                limit = tool_input.get("limit", 1000)
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
            for i, item in enumerate(items):
                if item.startswith('.'):
                    continue

                item_path = os.path.join(path, item)
                is_last = i == len(items) - 1

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

    def run_streaming_conversation(self, messages: list) -> dict:
        """Run a streaming conversation with Claude until completion"""
        output_tokens = 0

        # Continue conversation until no more tool calls
        while True:
            print(f"{Colors.BRIGHT_MAGENTA}[AI REQUEST]{Colors.END} Sending request to Claude with {len(messages)} messages:")
            for i, message in enumerate(messages):
                content_preview = self.truncate_for_debug(str(message['content']))
                print(f"  Message {i+1} ({message['role']}): {content_preview}")
            print()

            print(f"{Colors.BRIGHT_MAGENTA}[AI STREAMING]{Colors.END} Starting streaming response...")

            # Use the streaming helper for cleaner code
            with self.client.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=10000,
                temperature=0,
                system=IMPLEMENTATION_SYSTEM_PROMPT,
                tools=self.get_tools_schema(),
                messages=messages
            ) as stream:
                print(f"{Colors.BRIGHT_GREEN}[AI STREAMING]{Colors.END} Receiving response:")

                # Stream text as it arrives
                for text in stream.text_stream:
                    print(f"{Colors.GREY}{text}{Colors.END}", end="", flush=True)

                print()  # New line after streaming text

                # Get the final message with all content blocks
                final_message = stream.get_final_message()

            print(f"{Colors.BRIGHT_MAGENTA}[AI RESPONSE]{Colors.END} Streaming completed")
            print(f"  Output tokens: {final_message.usage.output_tokens}")
            output_tokens += final_message.usage.output_tokens

            # Add assistant message to conversation  
            messages.append({
                "role": "assistant", 
                "content": final_message.content
            })

            # Check if there are tool calls to execute
            tool_calls = [block for block in final_message.content if hasattr(block, 'type') and block.type == "tool_use"]

            if not tool_calls:
                print(f"{Colors.BRIGHT_GREEN}[CONVERSATION]{Colors.END} No more tool calls, conversation complete")
                break

            print(f"{Colors.BRIGHT_CYAN}[TOOL EXECUTION]{Colors.END} Processing {len(tool_calls)} tool calls")

            # Execute tool calls and collect results
            tool_results = []
            for tool_call in tool_calls:
                print(f"{Colors.BRIGHT_CYAN}[TOOL EXECUTION]{Colors.END} Executing tool: {tool_call.name}")
                result = self.execute_tool_call(tool_call.name, tool_call.input)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": json.dumps(result)
                })

                result_preview = self.truncate_for_debug(json.dumps(result))
                print(f"{Colors.BRIGHT_GREEN if result['success'] else Colors.BRIGHT_RED}[TOOL RESULT]{Colors.END} {tool_call.name}: {'Success' if result['success'] else 'Error'}")
                print(f"  Result: {result_preview}")

            # Add tool results to conversation
            messages.append({
                "role": "user",
                "content": tool_results
            })

        return {
            "messages": messages,
            "total_output_tokens": output_tokens
        }

    def implement_screen(self, screen_text: str):
        """Implement a screen by creating views and templates"""
        print(f"{Colors.BRIGHT_CYAN}[AGENT]{Colors.END} Starting screen implementation")
        print(f"  Screen text length: {len(screen_text)} characters")
        print(f"  Screen preview: {screen_text[:100]}...")

        # Read current models and views for context
        print(f"{Colors.BRIGHT_CYAN}[AGENT]{Colors.END} Gathering context files")
        models_content = self.read_file("web/models.py")
        views_content = self.read_file("web/views.py")
        urls_content = self.read_file("web/urls.py")

        # Get directory structure
        print(f"{Colors.BRIGHT_CYAN}[AGENT]{Colors.END} Generating directory tree")
        directory_tree = self.get_directory_tree(self.project_path)
        print(f"  Directory tree length: {len(directory_tree)} characters")

        # Create prompt for implementation
        prompt = f"""
<context name="project_structure">
{directory_tree}
</context>
<context name="models" path="web/models.py">
{models_content}
</context>
<context name="urls" path="web/urls.py">
{urls_content}
</context>
<screen>{screen_text}</screen>
"""

        print(f"{Colors.BRIGHT_CYAN}[PROMPT]{Colors.END} Generated prompt:")
        print(self.truncate_for_debug(prompt))
        print(f"{Colors.BRIGHT_MAGENTA}[AI REQUEST]{Colors.END} Sending request to Claude with tools")

        # Initialize token tracking
        messages = [{"role": "user", "content": prompt}]
        input_tokens = len(prompt.split()) + len(IMPLEMENTATION_SYSTEM_PROMPT.split())
        print(f"{Colors.BRIGHT_MAGENTA}[AI REQUEST]{Colors.END} Estimated input tokens: {input_tokens}")

        # Run the streaming conversation
        result = self.run_streaming_conversation(messages)

        print(f"{Colors.BRIGHT_GREEN}[IMPLEMENTATION]{Colors.END} Screen implementation completed")
        print(f"  Total input tokens: {input_tokens}")
        print(f"  Total output tokens: {result['total_output_tokens']}")

class ExecuteWork(Phase):
    def run(self, state: State, context: Context = None) -> dict:
        print(f"{Colors.BRIGHT_MAGENTA}=== EXECUTE WORK PHASE STARTED ==={Colors.END}")

        work = state["work"]
        project_path = state["project_path"]

        # Parse work into an array by extracting content between <screen> tags
        print(f"{Colors.BRIGHT_CYAN}[PARSING]{Colors.END} Parsing screens from work content...")
        screen_pattern = r'<screen[^>]*>(.*?)</screen>'
        screens = re.findall(screen_pattern, work, re.DOTALL)
        print(f"{Colors.BRIGHT_CYAN}[PARSING]{Colors.END} Found {len(screens)} screen matches with regex")

        # Clean up the extracted screens (remove leading/trailing whitespace)
        screens = [screen.strip() for screen in screens]

        print(f"{Colors.BRIGHT_GREEN}[PARSING]{Colors.END} Screen parsing completed:")
        print(f"  Found {len(screens)} screens after cleanup")

        # Print the array
        print(f"{Colors.BRIGHT_MAGENTA}[SCREENS]{Colors.END} Parsed screens array:")
        for i, screen in enumerate(screens):
            print(f"{Colors.BRIGHT_GREEN}Screen {i+1}:{Colors.END}")
            print(f"  Length: {len(screen)} characters")
            print(f"  Preview: {screen[:100]}..." if len(screen) > 100 else f"  Content: {screen}")
            print("-" * 40)

        # Create implementation agent
        print(f"{Colors.BRIGHT_YELLOW}[AGENT]{Colors.END} Creating implementation agent...")
        agent = ImplementationAgent(project_path)

        # Process each screen
        print(f"\n{Colors.BRIGHT_YELLOW}[PROCESSING]{Colors.END} Processing screens with implementation agent:")
        for i, screen in enumerate(screens):
            if i < 12:
                print(f"{Colors.BRIGHT_CYAN}=== Skipping screen {i+1}/{len(screens)} ==={Colors.END}")
                continue
            print(f"{Colors.BRIGHT_CYAN}=== Processing screen {i+1}/{len(screens)} ==={Colors.END}")
            print(f"Content preview: {screen[:100]}..." if len(screen) > 100 else f"Content: {screen}")

            # Implement the screen
            agent.implement_screen(screen)
            print(f"{Colors.BRIGHT_GREEN}[PROCESSING]{Colors.END} Screen {i+1} processing completed")
            print(f"  Agent history entries so far: {len(agent.history)}")
            print()

        print(f"{Colors.BRIGHT_MAGENTA}=== EXECUTE WORK PHASE COMPLETED ==={Colors.END}")
        print(f"{Colors.BRIGHT_YELLOW}[SUMMARY]{Colors.END} Final summary:")
        print(f"  Screens processed: {len(screens)}")
        print(f"  Agent history entries: {len(agent.history)}")
        print(f"  Agent history preview:")
        for i, entry in enumerate(agent.history[-5:]):  # Show last 5 entries
            print(f"    {i+1}. {entry}")

        return {
            "screens": screens,
            "implementation_history": agent.history
        }