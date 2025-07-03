import os
from data_serializer import text_file
from phase_manager import State, Phase, Context
from with_step import with_streaming_step

PLAN_SCREENS_SYSTEM_PROMPT = """
You are a senior web developer who specialized in Django.
Your job is to define user stories based on available spec and a data model. Each story may have screens.

Here's an example of few user stories for a blog:

<group name="...">
<story name="Post to blog">
<description>As a user, I am able to ...</description>
<screen name="Create post page" urlPattern="/post/new">
<frame>
<description>Provides a form to enter post details</description>
<action name="Create post"/>
</frame>
</screen>
</story>
<story name="See all posts">
<description>As a visitor, I am able to...</description>
<screen name="Post index" urlPattern="/post">
<frame>
<description>List of all posts</description>
</frame>
</story>
</group>

IMPORTANT: do not output anything except <group> and <story> sections
"""

def plan_stories_with_claude(spec: str, project_path: str, context: Context) -> str:

    with with_streaming_step("Planning user stories and screens...") as (input_tokens, output_tokens):
        response_text = ""
        models = read_models_file(project_path)
        prompt = f"<spec>{spec}</spec><models>{models}</models>"

        input_tokens[0] = len(prompt.split()) + len(PLAN_SCREENS_SYSTEM_PROMPT.split())

        with context.anthropic_client.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            temperature=0,
            system=PLAN_SCREENS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
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

class PlanScreens(Phase):
    description = "Generate a set of UI screens to implement (stories.txt)"

    def run(self, state: State, context: Context) -> dict:
        spec = state["spec"]
        project_path = state["project_path"]

        stories = plan_stories_with_claude(spec, project_path, context)

        return {
            "stories": stories
        }
    
    def get_state_schema_entries(self) -> dict[str, dict]:
        return {
            "stories": text_file("stories.txt")
        }
