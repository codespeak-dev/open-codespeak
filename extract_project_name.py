import os
import random
from colors import Colors
from state_machine import State, Transition
import anthropic

from with_step import with_step

PREFIXES = [
    'majestic', 'brilliant', 'crimson', 'azure', 'verdant', 'lively', 'silent', 'radiant', 'clever', 'mellow',
    'vivid', 'gentle', 'bold', 'swift', 'serene', 'amber', 'frosty', 'sunny', 'dusky', 'stellar'
]

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

def prefixed_project_name(base_name: str) -> str:
    prefix = random.choice(PREFIXES)
    return f"{prefix}_{base_name}"

class ExtractProjectName(Transition):
    def run(self, state: State) -> State:
        spec = state["spec"]
        with with_step("Extracting project name from Claude..."):
            project_name_base = extract_project_name(spec)
        project_name = prefixed_project_name(project_name_base)
        print(f"Project name: {Colors.BOLD}{Colors.BRIGHT_CYAN}{project_name}{Colors.END}")

        project_path = os.path.join(state["target_dir"], project_name)
        os.makedirs(project_path, exist_ok=True)

        return state.clone({
            "project_name": project_name,
            "project_path": project_path
        })