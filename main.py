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

def generate_django_project(project_name: str):
    os.makedirs(project_name, exist_ok=True)
    subprocess.run(["django-admin", "startproject", project_name, project_name], check=True)
    subprocess.run([sys.executable, "manage.py", "startapp", "web"], cwd=project_name, check=True)

def write_models_py(project_name: str, entities: list):
    models_path = os.path.join(project_name, 'web', 'models.py')
    with open(models_path, 'w') as f:
        f.write("from django.db import models\n\n")
        for entity in entities:
            f.write(f"class {entity['name']}(models.Model):\n")
            for field_name, field_type in entity['fields'].items():
                f.write(f"    {field_name} = models.{field_type}\n")
            f.write("\n")

def extract_project_name(prompt: str) -> str:
    """
    Uses Claude 3.5 to extract a Django project name from the prompt.
    """
    client = anthropic.Anthropic()
    system_prompt = """You are an expert Django developer. Given a user prompt, extract a concise, valid Python identifier to use as a Django project name. Only return the name, nothing else."""
    response = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=10,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}]
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

def add_app_to_installed_apps(project_name: str, app_name: str = "web"):
    settings_path = os.path.join(project_name, project_name, "settings.py")
    with open(settings_path, "r") as f:
        lines = f.readlines()
    new_lines = []
    added = False
    for idx, line in enumerate(lines):
        new_lines.append(line)
        if not added and line.strip().startswith("INSTALLED_APPS") and "[" in line:
            # Insert the app on the next line after INSTALLED_APPS = [
            new_lines.append(f"    '{app_name}',\n")
            added = True
    with open(settings_path, "w") as f:
        f.writelines(new_lines)

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

    generate_django_project(project_name)
    write_models_py(project_name, with_step_result['entities'])
    add_app_to_installed_apps(project_name, "web")

    def makemigrations():
        subprocess.run([sys.executable, "manage.py", "makemigrations", "web"], cwd=project_name, check=True)
    with with_step("Running makemigrations for 'web' app..."):
        makemigrations()
    print("makemigrations complete.")

    print(f"\nProject '{project_name}' generated with entities in web/models.py.")

if __name__ == "__main__":
    main()
