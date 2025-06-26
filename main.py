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
from typing import List, Dict, Optional
from pydantic import BaseModel

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
    shutil.copytree(template_dir, project_root)

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
        (f'{app_name}/views.py', os.path.join(project_name, app_name, 'views.py')),
        (f'{project_name}/asgi.py', os.path.join(project_settings_root, 'asgi.py')),
        (f'{project_name}/wsgi.py', os.path.join(project_settings_root, 'wsgi.py')),
        ('manage.py', os.path.join(project_name, 'manage.py')),
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
        "Example: {\"name\": \"Post\", \"fields\": {\"title\": \"CharField(max_length=100)\", \"author_id\": \"IntegerField()\"}, \"relationships\": {\"author\": {\"type\": \"ForeignKey\", \"related_to\": \"User\"}}}"
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


def main():
    parser = argparse.ArgumentParser(description="Generate Django project from file prompt via Claude.")
    parser.add_argument('filepath', help='Path to the input file')
    parser.add_argument('--target-dir', 
                       default=os.getenv('CODESPEAK_TARGET_DIR', '.'),
                       help='Target directory for the generated project (defaults to CODESPEAK_TARGET_DIR env var or current directory)')
    args = parser.parse_args()

    with open(args.filepath, 'r') as f:
        prompt = f.read()

    with_step_result = {}
    with with_step("Extracting project name from Claude..."):
        project_name_base = extract_project_name(prompt)
        with_step_result['project_name_base'] = project_name_base
    project_name = prefixed_project_name(with_step_result['project_name_base'])
    print(f"Project name: {Colors.BOLD}{Colors.BRIGHT_CYAN}{project_name}{Colors.END}")

    with with_step("Extracting models and fields from Claude..."):
        entities = extract_models_and_fields(prompt)
        with_step_result['entities'] = entities
    print("Entities extracted:")
    for entity in with_step_result['entities']:
        print(f"  - {Colors.BOLD}{Colors.BRIGHT_GREEN}{entity.name}{Colors.END}")
        for field, ftype in entity.fields.items():
            print(f"      {Colors.BRIGHT_YELLOW}{field}{Colors.END}: {ftype}")
        if entity.relationships:
            print(f"    {Colors.BRIGHT_MAGENTA}Relationships:{Colors.END}")
            for rel_field, rel_info in entity.relationships.items():
                print(f"      {Colors.BRIGHT_YELLOW}{rel_field}{Colors.END}: {rel_info['type']} -> {Colors.BRIGHT_GREEN}{rel_info['related_to']}{Colors.END}")

    # Create target directory if it doesn't exist
    os.makedirs(args.target_dir, exist_ok=True)
    
    # Generate project in the target directory
    project_path = os.path.join(args.target_dir, project_name)
    generate_django_project_from_template(args.target_dir, project_name, with_step_result['entities'], "web")

    def makemigrations():
        subprocess.run([sys.executable, "manage.py", "makemigrations", "web"], cwd=project_path, check=True)
    with with_step("Running makemigrations for 'web' app..."):
        makemigrations()
    print("makemigrations complete.")

    def migrate():
        subprocess.run([sys.executable, "manage.py", "migrate"], cwd=project_path, check=True)
    with with_step("Running migrate..."):
        migrate()
    print("migrate complete.")

    print(f"\nProject '{Colors.BOLD}{Colors.BRIGHT_CYAN}{project_name}{Colors.END}' generated in '{project_path}'.")

if __name__ == "__main__":
    main()
