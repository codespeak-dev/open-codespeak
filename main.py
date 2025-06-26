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

dotenv.load_dotenv()

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

def prefixed_project_name(base_name: str) -> str:
    prefix = random.choice(PREFIXES)
    return f"{prefix}_{base_name}"

def generate_django_project_from_template(project_name: str, entities: list, app_name: str = "web"):
    template_dir = "app_template"
    shutil.copytree(template_dir, project_name)

    shutil.move(
        os.path.join(project_name, '_project_'),
        os.path.join(project_name, project_name)
    )

    secret_key = secrets.token_urlsafe(50)
    env = Environment(loader=FileSystemLoader(project_name))
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

    files_to_template = [
        # (template_path, output_path)
        (f'{project_name}/settings.py', os.path.join(project_name, project_name, 'settings.py')),
        (f'{app_name}/models.py', os.path.join(project_name, app_name, 'models.py')),
        (f'{project_name}/asgi.py', os.path.join(project_name, project_name, 'asgi.py')),
        (f'{project_name}/wsgi.py', os.path.join(project_name, project_name, 'wsgi.py')),
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

def extract_models_and_fields(prompt: str) -> list:
    """
    Uses Claude 3.5 to extract a list of Django models and their fields from the prompt.
    Returns a list of dicts: [{"name": ..., "fields": {field_name: field_type, ...}}, ...]
    """
    client = anthropic.Anthropic()
    system_prompt = (
        "You are an expert Django developer. Given a user prompt, extract a list of Django models and their fields. "
        "Return a JSON array of objects, each with 'name' (model name) and 'fields' (object mapping field names to Django field types, e.g. 'CharField(max_length=100)'). "
        "Do not include any explanation, only valid JSON."
    )
    response = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=512,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}]
    )
    return json.loads(response.content[0].text.strip())


def main():
    parser = argparse.ArgumentParser(description="Generate Django project from file prompt via Claude.")
    parser.add_argument('filepath', help='Path to the input file')
    args = parser.parse_args()

    with open(args.filepath, 'r') as f:
        prompt = f.read()

    with_step_result = {}
    with with_step("Extracting project name from Claude..."):
        project_name_base = extract_project_name(prompt)
        with_step_result['project_name_base'] = project_name_base
    project_name = prefixed_project_name(with_step_result['project_name_base'])
    print(f"Project name: {project_name}")

    with with_step("Extracting models and fields from Claude..."):
        entities = extract_models_and_fields(prompt)
        with_step_result['entities'] = entities
    print("Entities extracted:")
    for entity in with_step_result['entities']:
        print(f"  - {entity['name']}")
        for field, ftype in entity['fields'].items():
            print(f"      {field}: {ftype}")

    generate_django_project_from_template(project_name, with_step_result['entities'], "web")

    def makemigrations():
        subprocess.run([sys.executable, "manage.py", "makemigrations", "web"], cwd=project_name, check=True)
    with with_step("Running makemigrations for 'web' app..."):
        makemigrations()
    print("makemigrations complete.")

    print(f"\nProject '{project_name}' generated with entities in web/models.py.")

if __name__ == "__main__":
    main()
