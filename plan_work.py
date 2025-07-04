from typing import Optional
from data_serializer import text_file
from phase_manager import State, Phase, Context
from with_step import with_streaming_step
from fileutils import load_prompt_template

SYSTEM_PROMPT = "You are a senior web developer who specialized in Django."

def plan_work(context: Context, user_prompt: str) -> str:

    with with_streaming_step("Planning work...") as (input_tokens, output_tokens):
        response_text = ""

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

class PlanWork(Phase):
    description = "Generate the work to be executed (work.txt)"

    def run(self, state: State, context: Context) -> dict:
        stories = state["stories"]
        spec_diff = state.get("spec_diff")
        old_stories = context.get_old_revision_blob("stories.txt")

        if spec_diff:
            user_prompt = load_prompt_template("plan_work",
                                             old_stories=old_stories, spec_diff=spec_diff,
                                             new_stories=stories, old_work=state["work"])
        else:
            user_prompt = load_prompt_template("plan_work", stories=stories)

        print(user_prompt)
        plan = plan_work(context, user_prompt)

        return {
            "work": plan
        }

    def get_state_schema_entries(self) -> dict[str, dict]:
        return {
            "work": text_file("work.txt")
        }
