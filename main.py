import argparse
import os
import subprocess
import sys
import anthropic
import json
import dotenv
from yaspin import yaspin
from yaspin.spinners import Spinners
from pprint import pprint
import random
import threading
import time
from contextlib import contextmanager
import shutil
from jinja2 import Environment, FileSystemLoader
import secrets
from typing import List, Dict, Optional, Tuple
from pydantic import BaseModel
import inquirer

from check_points import DJANGO_PROJECT_CREATED, DONE, ENTITIES_EXTRACTED, MAKEMIGRATIONS_COMPLETE, MIGRATIONS_COMPLETE, PROJECT_NAME_EXTRACTED, CheckPoints

dotenv.load_dotenv()

# ANSI color codes
class Colors:
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_MAGENTA = '\033[95m'
    BOLD = '\033[1m'
    END = '\033[0m'

@contextmanager
def with_step(text):
    stop_event = threading.Event()
    elapsed = [0]

    def update_spinner(spinner):
        while not stop_event.is_set():
            spinner.text = f"{text} ({elapsed[0]}s)"
            time.sleep(1)
            elapsed[0] += 1

    with yaspin(Spinners.dots, text=f"{text} (0s)") as spinner:
        t = threading.Thread(target=update_spinner, args=(spinner,))
        t.start()
        try:
            yield
        finally:
            stop_event.set()
            t.join()
            spinner.stop()
            sys.stdout.write("\r" + " " * (len(spinner.text) + 10) + "\r")
            sys.stdout.flush()
            print(f"{text} complete in {elapsed[0]}s.")

PREFIXES = [
    'majestic', 'brilliant', 'crimson', 'azure', 'verdant', 'lively', 'silent', 'radiant', 'clever', 'mellow',
    'vivid', 'gentle', 'bold', 'swift', 'serene', 'amber', 'frosty', 'sunny', 'dusky', 'stellar'
]

class EntityField(BaseModel):
    name: str
    field_type: str
    related_to: Optional[str] = None
    relationship_type: Optional[str] = None

class Entity(BaseModel):
    name: str
    fields: Dict[str, str]
    relationships: Dict[str, Dict[str, str]] = {}

def prefixed_project_name(base_name: str) -> str:
    prefix = random.choice(PREFIXES)
    return f"{prefix}_{base_name}"

def generate_django_project_from_template(target_dir: str, project_name: str, entities: List[Entity], app_name: str = "web"):
    template_dir = "app_template"
    project_root = os.path.join(target_dir, project_name)
    shutil.copytree(template_dir, project_root, dirs_exist_ok=True)

    shutil.move(
        os.path.join(project_root, '_project_'),
        os.path.join(project_root, project_name)
    )

    secret_key = secrets.token_urlsafe(50)
    env = Environment(loader=FileSystemLoader(project_root))
    context = {
        'project_name': project_name,
        'app_name': app_name,
        'secret_key': secret_key,
        'entities': entities
    }

    def render_and_write(template_path, output_path):
        template = env.get_template(template_path)
        content = template.render(context)
        with open(output_path, 'w') as f:
            f.write(content)


    project_settings_root = os.path.join(project_root, project_name)
    files_to_template = [
        # (template_path, output_path)
        (f'{project_name}/settings.py', os.path.join(project_settings_root, 'settings.py')),
        (f'{app_name}/models.py', os.path.join(project_root, app_name, 'models.py')),
        (f'{app_name}/views.py', os.path.join(project_root, app_name, 'views.py')),
        (f'{project_name}/asgi.py', os.path.join(project_settings_root, 'asgi.py')),
        (f'{project_name}/wsgi.py', os.path.join(project_settings_root, 'wsgi.py')),
        ('manage.py', os.path.join(project_root, 'manage.py')),
    ]

    for template_path, output_path in files_to_template:
        render_and_write(template_path, output_path)

def extract_project_name(prompt: str) -> str:
    """
    Uses Claude 3.5 to extract a Django project name from the prompt.
    Only the first 50 lines of the prompt are used.
    """
    # Limit prompt to first 50 lines
    prompt_limited = "\n".join(prompt.splitlines()[:50])
    client = anthropic.Anthropic()
    system_prompt = """You are an expert Django developer. Given a user prompt, extract a concise, valid Python identifier to use as a Django project name. Only return the name, nothing else."""
    response = client.messages.create(
        model="claude-3-5-haiku-latest",
        max_tokens=10,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt_limited}]
    )
    return response.content[0].text.strip()

def add_import_to_file(file_path: str, import_statement: str):
    """
    Add an import statement to the top of a Python file after existing imports.
    """
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    # Find the last import line
    last_import_index = 0
    for i, line in enumerate(lines):
        if line.strip().startswith(('import ', 'from ')) and not line.strip().startswith('#'):
            last_import_index = i
    
    # Insert the new import after the last import
    if import_statement.strip() + '\n' not in lines:
        lines.insert(last_import_index + 1, import_statement.strip() + '\n')
        
        with open(file_path, 'w') as f:
            f.writelines(lines)

def fix_missing_imports(error_output: str, models_file_path: str) -> bool:
    """
    Use Claude to detect missing imports from error output and fix them using tool calls.
    Returns True if fixes were applied, False otherwise.
    """
    client = anthropic.Anthropic()
    system_prompt = (
        "You are an expert Python/Django developer. Given an error output from Django makemigrations, "
        "identify any missing import statements needed to fix NameError issues. "
        "Use the add_import tool to add each missing import statement. "
        "Only call the tool for imports that are actually needed to fix the errors."
    )
    
    tools = [
        {
            "name": "add_import",
            "description": "Add an import statement to fix missing imports",
            "input_schema": {
                "type": "object",
                "properties": {
                    "import_statement": {
                        "type": "string",
                        "description": "The complete import statement (e.g., 'import uuid' or 'from django.contrib.auth.models import User')"
                    }
                },
                "required": ["import_statement"]
            }
        }
    ]
    
    response = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=512,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Error output:\n{error_output}"}],
        tools=tools
    )
    
    applied_fixes = False
    for content_block in response.content:
        if content_block.type == "tool_use" and content_block.name == "add_import":
            import_statement = content_block.input["import_statement"]
            print(f"    {Colors.BRIGHT_CYAN}+{Colors.END} {import_statement}")
            add_import_to_file(models_file_path, import_statement)
            applied_fixes = True
    
    return applied_fixes

def extract_models_and_fields(prompt: str) -> List[Entity]:
    """
    Uses Claude 3.5 to extract a list of Django models and their fields from the prompt.
    Returns a list of Entity objects with fields and relationships.
    """
    client = anthropic.Anthropic()
    system_prompt = (
        "You are an expert Django developer. Given a user prompt, extract a list of Django models and their fields. "
        "Return a JSON array of objects, each with:"
        "- 'name' (model name)"
        "- 'fields' (object mapping field names to Django field types, e.g. 'CharField(max_length=100)')"
        "- 'relationships' (object mapping field names to relationship info with 'type' and 'related_to' keys)"
        "For relationships, use types like 'ForeignKey', 'ManyToManyField', 'OneToOneField'."
        "IMPORTANT: If there's an intermediate model (like RSVP) that connects two other models (like User and Event), "
        "do NOT create direct ManyToManyField relationships between the connected models. "
        "The intermediate model's ForeignKey relationships are sufficient to represent the many-to-many connection."
        "Example: {\"name\": \"Post\", \"fields\": {\"title\": \"CharField(max_length=100)\"}, \"relationships\": {\"author\": {\"type\": \"ForeignKey\", \"related_to\": \"User\"}}}"
        "Do not include any explanation, only valid JSON."
    )
    response = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=1024,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}]
    )
    raw_data = json.loads(response.content[0].text.strip())
    return [Entity(**item) for item in raw_data]

def refine_entities(original_prompt: str, entities: List[Entity], feedback: str) -> List[Entity]:
    """
    Use Claude to refine entities based on user feedback.
    """
    client = anthropic.Anthropic()
    
    # Convert entities to JSON for the prompt
    entities_json = json.dumps([{
        "name": entity.name,
        "fields": entity.fields,
        "relationships": entity.relationships
    } for entity in entities], indent=2)
    
    system_prompt = (
        "You are an expert Django developer. Given the original user prompt, current entities, and user feedback, "
        "modify the entities accordingly. Return a JSON array of objects with the same structure: "
        "- 'name' (model name)"
        "- 'fields' (object mapping field names to Django field types)"
        "- 'relationships' (object mapping field names to relationship info with 'type' and 'related_to' keys)"
        "Only return the JSON array, no explanation."
    )
    
    user_message = f"""Original prompt:
{original_prompt}

Current entities:
{entities_json}

User feedback:
{feedback}

Please modify the entities based on the feedback."""
    
    response = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=1024,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )
    
    raw_data = json.loads(response.content[0].text.strip())
    return [Entity(**item) for item in raw_data]

def display_entities(entities: List[Entity]):
    """Display entities in a formatted way"""
    print("Entities extracted:")
    for entity in entities:
        print(f"  - {Colors.BOLD}{Colors.BRIGHT_GREEN}{entity.name}{Colors.END}")
        for rel_field, rel_info in entity.relationships.items():
            print(f"      {Colors.BRIGHT_MAGENTA}{rel_field}{Colors.END}: {rel_info['type']} -> {Colors.BRIGHT_GREEN}{rel_info['related_to']}{Colors.END}")
        for field, ftype in entity.fields.items():
            print(f"      {Colors.BRIGHT_YELLOW}{field}{Colors.END}: {ftype}")

def get_entities_confirmation(entities: List[Entity], original_prompt: str = "") -> Tuple[bool, List[Entity]]:
    """
    Ask user to confirm entities or provide feedback for changes.
    Returns (should_proceed, final_entities)
    """
    current_entities = entities
    
    while True:
        display_entities(current_entities)
        print(f"\n{Colors.BOLD}Please review the extracted entities:{Colors.END}")
        
        questions = [
            inquirer.List(
                'action',
                message="What would you like to do?",
                choices=[
                    ('Yes, proceed with these entities', 'proceed'),
                    ('Modify the entities', 'modify')
                ],
                carousel=True
            )
        ]
        
        try:
            answers = inquirer.prompt(questions)
            if not answers:  # User pressed Ctrl+C
                print(f"\n{Colors.BRIGHT_YELLOW}Cancelled by user{Colors.END}")
                sys.exit(0)
            
            action = answers['action']
            
            if action == 'proceed':
                return True, current_entities
            elif action == 'modify':
                feedback_question = [
                    inquirer.Text(
                        'feedback',
                        message="What would you like to change?",
                        validate=lambda _, x: len(x.strip()) > 0 or "Please provide feedback"
                    )
                ]
                
                feedback_answers = inquirer.prompt(feedback_question)
                if not feedback_answers:
                    continue
                
                feedback = feedback_answers['feedback']
                print(f"\n{Colors.BRIGHT_CYAN}Refining entities...{Colors.END}")
                current_entities = refine_entities(original_prompt, current_entities, feedback)
                print(f"{Colors.BRIGHT_GREEN}Entities updated{Colors.END}\n")
                
        except KeyboardInterrupt:
            print(f"\n{Colors.BRIGHT_YELLOW}Cancelled by user{Colors.END}")
            sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Generate Django project from file prompt via Claude.")
    parser.add_argument('filepath', help='Path to the input file')
    parser.add_argument('--target-dir', 
                       default=os.getenv('CODESPEAK_TARGET_DIR', '.'),
                       help='Target directory for the generated project (defaults to CODESPEAK_TARGET_DIR env var or current directory)')
    parser.add_argument('--incremental', help='Path to the project output dir')
    args = parser.parse_args()

    spec_file = args.filepath
    cp = None
    if args.incremental:
        cp = CheckPoints(args.incremental)
        spec_file = cp.spec_file
        print(f"Running in incremental mode:")
        print(f"  * Spec file: {spec_file}")
        print(f"  * Target dir: {args.incremental}")

    with open(spec_file, 'r') as f:
        prompt = f.read()

    if not cp:
        # Fresh run, no checkpoints to restore from
        with_step_result = {}
        with with_step("Extracting project name from Claude..."):
            project_name_base = extract_project_name(prompt)
            with_step_result['project_name_base'] = project_name_base
        project_name = prefixed_project_name(with_step_result['project_name_base'])
        print(f"Project name: {Colors.BOLD}{Colors.BRIGHT_CYAN}{project_name}{Colors.END}")

        # Generate project in the target directory
        project_path = os.path.join(args.target_dir, project_name)

        # Create project directory if it doesn't exist
        os.makedirs(project_path, exist_ok=True)

        cp = CheckPoints(project_path, args.filepath)
        cp.save(PROJECT_NAME_EXTRACTED)
    else:
        project_path = cp.target_dir

    with cp.checkpoint(ENTITIES_EXTRACTED):
        with with_step("Extracting models and fields from Claude..."):
            entities = extract_models_and_fields(prompt)
            with_step_result['entities'] = entities
        
        # Get user confirmation for entities
        should_proceed, final_entities = get_entities_confirmation(with_step_result['entities'], prompt)
        if not should_proceed:
            print(f"{Colors.BRIGHT_YELLOW}Project generation cancelled{Colors.END}")
            sys.exit(0)
        with_step_result['entities'] = final_entities

    # Generate project in the target directory
    with cp.checkpoint(DJANGO_PROJECT_CREATED):
        generate_django_project_from_template(args.target_dir, project_name, with_step_result['entities'], "web")

    with cp.checkpoint(MAKEMIGRATIONS_COMPLETE):
        def makemigrations():
            max_retries = 3
            models_file_path = os.path.join(project_path, "web", "models.py")
            
            for attempt in range(max_retries):
                try:
                    result = subprocess.run(
                        [sys.executable, "manage.py", "makemigrations", "web"], 
                        cwd=project_path, 
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    return  # Success
                except subprocess.CalledProcessError as e:
                    if attempt < max_retries - 1 and "NameError" in e.stderr:
                        print(f"  {Colors.BRIGHT_YELLOW}→{Colors.END} Detected missing imports, auto-fixing...")
                        if fix_missing_imports(e.stderr, models_file_path):
                            print(f"  {Colors.BRIGHT_GREEN}✓{Colors.END} Imports fixed, retrying...")
                            continue  # Retry with fixed imports
                    # Re-raise the error if we can't fix it or max retries reached
                    raise
                    
        with with_step("Running makemigrations for 'web' app..."):
            makemigrations()
        print("makemigrations complete.")

    with cp.checkpoint(MIGRATIONS_COMPLETE):
        def migrate():
            subprocess.run([sys.executable, "manage.py", "migrate"], cwd=project_path, check=True)
        with with_step("Running migrate..."):
            migrate()
        print("migrate complete.")

    with cp.checkpoint(DONE):
        print(f"\nProject '{Colors.BOLD}{Colors.BRIGHT_CYAN}{project_name}{Colors.END}' generated in '{project_path}'.")

if __name__ == "__main__":
    main()
