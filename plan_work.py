from typing import Dict
import llm_cache
from data_serializer import text_file
from phase_manager import State, Phase, Context
from with_step import with_streaming_step

PLAN_SCREENS_SYSTEM_PROMPT = """
You are a senior web developer who specialized in Django.
You have a list of user stories and screens that need to be implemented in an app.
You need to order them as steps, starting from those that need to be implemented first and finishing with those that have more dependencies.

Example of output:

<step>
<overall_goal>
    <!-- A single, concise sentence describing the user's high-level objective. -->
</overall_goal>

<key_knowledge>
    <!-- Crucial facts, conventions, and constraints the agent must remember based on the conversation history and interaction with the user. Use bullet points. -->
</key_knowledge>

<current_plan>
    <!-- The agent's step-by-step plan. Mark completed steps. -->
</current_plan>
</step>
<step>
...
</step>

The output will be parsed by XML parser. It must be valid XML.
"""

def plan_work_with_claude(spec: str, stories: str, project_path: str) -> str:
    client = llm_cache.Anthropic()

    with with_streaming_step("Planning work...") as (input_tokens, output_tokens):
        response_text = ""
        prompt = f"<stories>{stories}</stories>"

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

class PlanWork(Phase):
    description = "Generate the work to be executed (work.txt)"

    def run(self, state: State, context: Context | None = None) -> dict:
        spec = state["spec"]
        project_path = state["project_path"]
        verbose = context.verbose if context else False

        stories = state["stories"]

        plan = plan_work_with_claude(spec, stories, project_path)

        return {
            "work": plan
        }

    def get_state_schema_entries(self) -> Dict[str, dict]:
        return {
            "work": text_file("work.txt")
        }