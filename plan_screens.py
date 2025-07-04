import os
import logging
from typing import Optional
from data_serializer import text_file
from phase_manager import State, Phase, Context
from with_step import with_streaming_step
from fileutils import load_prompt_template

SYSTEM_PROMPT = "You are a senior web developer who specialized in Django."

def plan_stories(project_path: str, context: Context, spec: Optional[str] = None, 
                           old_spec: Optional[str] = None, new_spec: Optional[str] = None, 
                           old_stories: Optional[str] = None, old_models: Optional[str] = None, 
                           new_models: Optional[str] = None) -> str:
    
    is_incremental = old_spec is not None
    step_message = "Planning user stories and screens incrementally..." if is_incremental else "Planning user stories and screens..."
    
    with with_streaming_step(step_message) as (input_tokens, output_tokens):
        response_text = ""
        
        if is_incremental:
            user_prompt = load_prompt_template("plan_screens", incremental=True, 
                                             old_spec=old_spec, new_spec=new_spec, 
                                             old_stories=old_stories, old_models=old_models, 
                                             new_models=new_models)
        else:
            models = read_models_file(project_path)
            user_prompt = load_prompt_template("plan_screens", incremental=False, spec=spec, models=models)

        input_tokens[0] = len(user_prompt.split()) + len(SYSTEM_PROMPT.split())

        with context.anthropic_client.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=20000,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}]
        ) as stream:
            for text in stream.text_stream:
                response_text += text
                output_tokens[0] += len(text.split())

    return response_text.strip()

def read_models_file(project_path: str) -> str:
    models_path = os.path.join(project_path, "web", "models.py")
    if not os.path.exists(models_path):
        raise FileNotFoundError(f"models.py not found at {models_path}")

    with open(models_path, 'r') as f:
        return f.read()

def read_stories_file(project_path: str) -> str:
    stories_path = os.path.join(project_path, "stories.txt")
    if not os.path.exists(stories_path):
        return ""

    with open(stories_path, 'r') as f:
        return f.read()

class PlanScreens(Phase):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__class__.__qualname__)
    description = "Generate a set of UI screens to implement (stories.txt)"

    def run(self, state: State, context: Context) -> dict:
        project_path = state["project_path"]
        spec_diff = state.get("spec_diff")

        if spec_diff:
            old_spec: str = context.get_old_revision_blob("spec.md")
            new_spec: str = state["spec"]
            old_stories: str = context.get_old_revision_blob("stories.txt")
            old_models: str = context.get_old_revision_blob("web/models.py")
            new_models: str = read_models_file(project_path)

            stories = plan_stories(
                project_path, context,
                old_spec=old_spec, new_spec=new_spec, 
                old_stories=old_stories, old_models=old_models, 
                new_models=new_models
            )
        else:
            spec = state["spec"]
            stories = plan_stories(project_path, context, spec=spec)

        return {
            "stories": stories
        }
    
    def get_state_schema_entries(self) -> dict[str, dict]:
        return {
            "stories": text_file("stories.txt")
        }
