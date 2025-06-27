import anthropic
import os
import re
from colors import Colors
from state_machine import State, Transition, Context
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

# def parse_screens(screens_text: str) -> list[dict]:
#     screens = []

#     # First, find all screen blocks using a simple pattern
#     screen_blocks = re.findall(r'<screen[^>]*>(.*?)</screen>', screens_text, re.DOTALL | re.IGNORECASE)

#     # Also extract the opening tags to parse attributes
#     opening_tags = re.findall(r'<screen[^>]*>', screens_text, re.IGNORECASE)

#     if len(screen_blocks) != len(opening_tags):
#         # Fallback: find complete screen elements
#         complete_matches = re.findall(r'(<screen[^>]*>)(.*?)</screen>', screens_text, re.DOTALL | re.IGNORECASE)
#         opening_tags = [match[0] for match in complete_matches]
#         screen_blocks = [match[1] for match in complete_matches]

#     for opening_tag, description in zip(opening_tags, screen_blocks):
#         # Parse attributes from the opening tag
#         attributes = {}

#         # Extract name attribute
#         name_match = re.search(r'name="([^"]*)"', opening_tag, re.IGNORECASE)
#         if name_match:
#             attributes['name'] = name_match.group(1).strip()

#         # Extract urlPattern attribute
#         url_match = re.search(r'urlPattern="([^"]*)"', opening_tag, re.IGNORECASE)
#         if url_match:
#             attributes['urlPattern'] = url_match.group(1).strip()

#         # Extract summary attribute
#         summary_match = re.search(r'summary="([^"]*)"', opening_tag, re.IGNORECASE)
#         if summary_match:
#             attributes['summary'] = summary_match.group(1).strip()

#         # Create screen object with all attributes
#         screen = {
#             "name": attributes.get('name', ''),
#             "urlPattern": attributes.get('urlPattern', ''),
#             "summary": attributes.get('summary', ''),
#             "description": description.strip()
#         }

#         screens.append(screen)

#     return screens

def plan_stories_with_claude(spec: str, project_path: str) -> str:
    client = anthropic.Anthropic()

    with with_streaming_step("Planning user stories and screens...") as (input_tokens, output_tokens):
        response_text = ""
        models = read_models_file(project_path)
        prompt = f"<spec>{spec}</spec><models>{models}</models>"

        input_tokens[0] = len(prompt.split()) + len(PLAN_SCREENS_SYSTEM_PROMPT.split())

        with client.messages.stream(
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

class PlanScreens(Transition):
    def run(self, state: State, context: Context = None) -> State:
        spec = state["spec"]
        project_path = state["project_path"]
        verbose = context.verbose if context else False

        stories = plan_stories_with_claude(spec, project_path)

        # if verbose:
        #     print(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}Planned Screens:{Colors.END}")
        #     for screen in screens:
        #         print(f"  {Colors.BRIGHT_GREEN}• {screen['name']}{Colors.END}: {screen['summary']}")
        #         print()

        # else:
        #     print(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}Planned {len(screens)} screens{Colors.END}")

        return state.clone({
            "stories": stories
        })
