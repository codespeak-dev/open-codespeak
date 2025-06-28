import anthropic
import os
import re
from colors import Colors
from state_machine import State, Transition, Context
from with_step import with_streaming_step

IMPLEMENTATION_SYSTEM_PROMPT = """
You are a Django developer tasked with implementing screens by creating Django views and HTML templates.

You have access to the following tools:
- list_files(path): List files in a directory
- read_file(file_path): Read contents of a file  
- edit_file(file_path, old_content, new_content): Edit a file by replacing old_content with new_content

You have access to the project's models.py and views.py files in context.

Your task is to implement each screen by:
1. Creating appropriate Django view functions in views.py
2. Creating HTML template files in the templates directory
3. Adding URL patterns to urls.py if needed

For each screen, parse the name, URL pattern, description and actions.
Create clean, functional Django code that follows best practices.

Always track your actions in history by calling the appropriate functions.

IMPORTANT: Only output valid Python code for file operations. Do not include explanations or comments unless specifically requested.
"""

class ImplementationAgent:
    def __init__(self, project_path: str):
        print(f"{Colors.BRIGHT_BLUE}[AGENT INIT]{Colors.END} Creating ImplementationAgent")
        print(f"  Project path: {project_path}")
        self.project_path = project_path
        self.history = []
        self.client = anthropic.Anthropic()
        print(f"{Colors.BRIGHT_BLUE}[AGENT INIT]{Colors.END} Agent initialized successfully")

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

    def read_file(self, file_path: str):
        """Read contents of a file"""
        print(f"{Colors.BRIGHT_YELLOW}[FILE OP]{Colors.END} Reading file: {file_path}")
        full_path = os.path.join(self.project_path, file_path) if not os.path.isabs(file_path) else file_path
        print(f"  Full path: {full_path}")

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"{Colors.BRIGHT_GREEN}[FILE OP]{Colors.END} Read {len(content)} characters, {len(content.splitlines())} lines")
            self.history.append(f"Read file: {file_path}")
            return content
        except Exception as e:
            error_msg = f"Error reading file {file_path}: {str(e)}"
            print(f"{Colors.BRIGHT_RED}[FILE OP ERROR]{Colors.END} {error_msg}")
            self.history.append(error_msg)
            return ""

    def edit_file(self, file_path: str, old_content: str, new_content: str):
        """Edit a file by replacing old_content with new_content"""
        print(f"{Colors.BRIGHT_YELLOW}[FILE OP]{Colors.END} Editing file: {file_path}")
        print(f"  Old content length: {len(old_content)}")
        print(f"  New content length: {len(new_content)}")
        full_path = os.path.join(self.project_path, file_path) if not os.path.isabs(file_path) else file_path

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
            print(f"  Current file size: {len(current_content)} characters")

            if old_content in current_content:
                updated_content = current_content.replace(old_content, new_content)
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(updated_content)
                print(f"{Colors.BRIGHT_GREEN}[FILE OP]{Colors.END} Successfully edited file")
                print(f"  New file size: {len(updated_content)} characters")
                self.history.append(f"Edited file: {file_path}")
                return True
            else:
                print(f"{Colors.BRIGHT_RED}[FILE OP ERROR]{Colors.END} Old content not found in file")
                print(f"  Looking for: {old_content[:50]}...")
                self.history.append(f"Old content not found in {file_path}")
                return False
        except Exception as e:
            error_msg = f"Error editing file {file_path}: {str(e)}"
            print(f"{Colors.BRIGHT_RED}[FILE OP ERROR]{Colors.END} {error_msg}")
            self.history.append(error_msg)
            return False

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

    def implement_screen(self, screen_text: str):
        """Implement a screen by creating views and templates"""
        print(f"{Colors.BRIGHT_CYAN}[AGENT]{Colors.END} Starting screen implementation")
        print(f"  Screen text length: {len(screen_text)} characters")
        print(f"  Screen preview: {screen_text[:100]}...")

        # Read current models and views for context
        print(f"{Colors.BRIGHT_CYAN}[AGENT]{Colors.END} Gathering context files")
        models_content = self.read_file("web/models.py")
        views_content = self.read_file("web/views.py")

        # Get directory structure
        print(f"{Colors.BRIGHT_CYAN}[AGENT]{Colors.END} Generating directory tree")
        directory_tree = self.get_directory_tree(self.project_path)
        print(f"  Directory tree length: {len(directory_tree)} characters")

        # Create prompt for implementation
        prompt = f"""
        <project_structure>
{directory_tree}
        </project_structure>
        <models>{models_content}</models>
        <current_views>{views_content}</current_views>
        <screen>{screen_text}</screen>

        Implement this screen by:
        1. Creating Django view function
        2. Creating HTML template
        3. Updating URLs if needed

        Provide the implementation code.
        """

        print(f"{Colors.BRIGHT_MAGENTA}[AI REQUEST]{Colors.END} Sending request to Claude")
        print(f"  Model: claude-sonnet-4-20250514")
        print(f"  Prompt length: {len(prompt)} characters")
        print(f"  System prompt length: {len(IMPLEMENTATION_SYSTEM_PROMPT)} characters")

        with with_streaming_step("Implementing screen...") as (input_tokens, output_tokens):
            response_text = ""
            input_tokens[0] = len(prompt.split()) + len(IMPLEMENTATION_SYSTEM_PROMPT.split())
            print(f"{Colors.BRIGHT_MAGENTA}[AI REQUEST]{Colors.END} Estimated input tokens: {input_tokens[0]}")

            with self.client.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=10000,
                temperature=0,
                system=IMPLEMENTATION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            ) as stream:
                for text in stream.text_stream:
                    response_text += text
                    output_tokens[0] += len(text.split())

        print(f"{Colors.BRIGHT_MAGENTA}[AI RESPONSE]{Colors.END} Received response")
        print(f"  Response length: {len(response_text)} characters")
        print(f"  Input tokens: {input_tokens[0]}")
        print(f"  Output tokens: {output_tokens[0]}")
        print(f"  Response preview: {response_text[:200]}...")

        # Process the response to extract and apply changes
        self.process_implementation_response(response_text, screen_text)

    def process_implementation_response(self, response: str, screen_text: str):
        """Process the AI response to extract and apply implementation changes"""
        print(f"{Colors.BRIGHT_CYAN}[RESPONSE PROCESSING]{Colors.END} Processing AI response")
        print(f"  Response length: {len(response)} characters")
        print(f"  Screen text length: {len(screen_text)} characters")

        # Extract code blocks and file operations from the response
        code_blocks = re.findall(r'```(?:python|html|django)?\n(.*?)\n```', response, re.DOTALL)
        print(f"{Colors.BRIGHT_CYAN}[RESPONSE PROCESSING]{Colors.END} Extracted {len(code_blocks)} code blocks")
        for i, block in enumerate(code_blocks):
            print(f"  Code block {i+1}: {len(block)} characters")

        # Look for file operations in the response
        file_operations = []

        # Look for patterns like "create file:", "edit file:", "update file:"
        file_op_patterns = [
            r'(?:create|write|add)\s+(?:file\s+)?["\']?([^"\':\s]+)["\']?:',
            r'(?:edit|update|modify)\s+(?:file\s+)?["\']?([^"\':\s]+)["\']?:',
            r'file_path\s*=\s*["\']([^"\']+)["\']'
        ]

        for pattern in file_op_patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            file_operations.extend(matches)

        print(f"{Colors.BRIGHT_CYAN}[RESPONSE PROCESSING]{Colors.END} Identified {len(file_operations)} potential file operations")
        for op in file_operations:
            print(f"  File operation: {op}")

        # For now, just log the response since the actual implementation parsing
        # would require more sophisticated parsing of the AI response
        print(f"{Colors.BRIGHT_CYAN}[RESPONSE PROCESSING]{Colors.END} Processing completed")
        print(f"  Status: logged for review")
        print(f"  Next steps: implement response parsing and file operations")

        self.history.append(f"Generated implementation for screen")
        print(f"{Colors.BRIGHT_GREEN}Implementation generated and logged{Colors.END}")

class ExecuteWork(Transition):
    def run(self, state: State, context: Context = None) -> dict:
        print(f"{Colors.BRIGHT_MAGENTA}=== EXECUTE WORK TRANSITION STARTED ==={Colors.END}")

        work = state["work"]
        project_path = state["project_path"]

        print(f"{Colors.BRIGHT_YELLOW}[STATE]{Colors.END} Initial state:")
        print(f"  Work length: {len(work)} characters")
        print(f"  Project path: {project_path}")
        print(f"  Work preview: {work[:200]}...")

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
            print(f"{Colors.BRIGHT_CYAN}=== Processing screen {i+1}/{len(screens)} ==={Colors.END}")
            print(f"Content preview: {screen[:100]}..." if len(screen) > 100 else f"Content: {screen}")

            # Implement the screen
            agent.implement_screen(screen)
            print(f"{Colors.BRIGHT_GREEN}[PROCESSING]{Colors.END} Screen {i+1} processing completed")
            print(f"  Agent history entries so far: {len(agent.history)}")
            print()

        print(f"{Colors.BRIGHT_MAGENTA}=== EXECUTE WORK TRANSITION COMPLETED ==={Colors.END}")
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