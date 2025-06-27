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
        self.project_path = project_path
        self.history = []
        self.client = anthropic.Anthropic()

    def list_files(self, path: str):
        """List files in a directory"""
        full_path = os.path.join(self.project_path, path) if not os.path.isabs(path) else path
        try:
            files = os.listdir(full_path)
            self.history.append(f"Listed files in {path}: {files}")
            return files
        except Exception as e:
            error_msg = f"Error listing files in {path}: {str(e)}"
            self.history.append(error_msg)
            return []

    def read_file(self, file_path: str):
        """Read contents of a file"""
        full_path = os.path.join(self.project_path, file_path) if not os.path.isabs(file_path) else file_path
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.history.append(f"Read file: {file_path}")
            return content
        except Exception as e:
            error_msg = f"Error reading file {file_path}: {str(e)}"
            self.history.append(error_msg)
            return ""

    def edit_file(self, file_path: str, old_content: str, new_content: str):
        """Edit a file by replacing old_content with new_content"""
        full_path = os.path.join(self.project_path, file_path) if not os.path.isabs(file_path) else file_path
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                current_content = f.read()

            if old_content in current_content:
                updated_content = current_content.replace(old_content, new_content)
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(updated_content)
                self.history.append(f"Edited file: {file_path}")
                return True
            else:
                error_msg = f"Old content not found in {file_path}"
                self.history.append(error_msg)
                return False
        except Exception as e:
            error_msg = f"Error editing file {file_path}: {str(e)}"
            self.history.append(error_msg)
            return False

    def write_file(self, file_path: str, content: str):
        """Write content to a new file"""
        full_path = os.path.join(self.project_path, file_path) if not os.path.isabs(file_path) else file_path
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.history.append(f"Created file: {file_path}")
            return True
        except Exception as e:
            error_msg = f"Error writing file {file_path}: {str(e)}"
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
        print(f"{Colors.CYAN}Implementing screen{Colors.RESET}")

        # Read current models and views for context
        models_content = self.read_file("web/models.py")
        views_content = self.read_file("web/views.py")

        # Get directory structure
        directory_tree = self.get_directory_tree(self.project_path)

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

        with with_streaming_step("Implementing screen...") as (input_tokens, output_tokens):
            response_text = ""
            input_tokens[0] = len(prompt.split()) + len(IMPLEMENTATION_SYSTEM_PROMPT.split())

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

        # Process the response to extract and apply changes
        self.process_implementation_response(response_text, screen_text)

    def process_implementation_response(self, response: str, screen_text: str):
        """Process the AI response to extract and apply implementation changes"""
        # This would parse the response and apply the changes
        # For now, just log the response
        self.history.append(f"Generated implementation for screen")
        print(f"{Colors.GREEN}Implementation generated{Colors.RESET}")

class ExecuteWork(Transition):
    def run(self, state: State, context: Context = None) -> State:
        work = state["work"]
        project_path = state["project_path"]

        # Parse work into an array by extracting content between <screen> tags
        screen_pattern = r'<screen[^>]*>(.*?)</screen>'
        screens = re.findall(screen_pattern, work, re.DOTALL)

        # Clean up the extracted screens (remove leading/trailing whitespace)
        screens = [screen.strip() for screen in screens]

        # Print the array
        print(f"{Colors.BLUE}Parsed screens array:{Colors.RESET}")
        for i, screen in enumerate(screens):
            print(f"{Colors.GREEN}Screen {i+1}:{Colors.RESET}")
            print(screen)
            print("-" * 40)

        # Create implementation agent
        agent = ImplementationAgent(project_path)

        # Process each screen
        print(f"\n{Colors.YELLOW}Processing screens with implementation agent:{Colors.RESET}")
        for i, screen in enumerate(screens):
            print(f"{Colors.CYAN}Processing screen {i+1}:{Colors.RESET}")
            print(f"Content: {screen[:100]}..." if len(screen) > 100 else f"Content: {screen}")

            # Implement the screen
            agent.implement_screen(screen)
            print()

        return state.clone({
            "screens": screens,
            "implementation_history": agent.history
        })