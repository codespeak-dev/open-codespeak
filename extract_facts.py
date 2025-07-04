import logging
from typing import Optional
from colors import Colors
from data_serializer import text_file
from phase_manager import State, Phase, Context
from with_step import with_streaming_step
from fileutils import load_prompt_template, format_file_content

SYSTEM_PROMPT = "You are an expert at analyzing project specifications and extracting key facts."

def extract_facts(context: Context, spec: str, stories: Optional[str] = None,
                 spec_diff: Optional[str] = None, old_stories: Optional[str] = None,
                 new_stories: Optional[str] = None, old_facts: Optional[str] = None) -> str:

    is_incremental = spec_diff is not None

    with with_streaming_step("Extracting general facts...") as (input_tokens, output_tokens):
        if is_incremental:
            user_prompt = load_prompt_template("extract_facts", incremental=True,
                                             spec=spec, spec_diff=spec_diff,
                                             old_stories=old_stories, new_stories=new_stories,
                                             old_facts=old_facts)
        else:
            user_prompt = load_prompt_template("extract_facts", incremental=False,
                                             spec=spec, stories=stories)

        input_tokens[0] = len(user_prompt.split()) + len(SYSTEM_PROMPT.split())

        logging.getLogger(ExtractFacts.__class__.__qualname__).info(user_prompt)

        response_text = ""
        with context.anthropic_client.stream(
            model="claude-3-7-sonnet-latest",
            max_tokens=16000,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
        ) as stream:
            for text in stream.text_stream:
                response_text += text
                output_tokens[0] += len(text.split())

        return response_text

class ExtractFacts(Phase):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__class__.__qualname__)

    def run(self, state: State, context: Context) -> dict:
        spec_diff = state.get("spec_diff")
        spec = state["spec"]

        if spec_diff:
            stories: str = state.get("stories")
            if not stories:
                raise ValueError("No stories found")
            old_facts: str = state.get("facts")

            spec, _ = format_file_content(spec, offset=None, limit=None, truncate_line=None)

            facts = extract_facts(context, spec=spec, spec_diff=spec_diff,
                                stories=stories,
                                old_facts=old_facts)
        else:
            stories = state.get("stories")
            if not stories:
                raise ValueError("No stories found")

            facts = extract_facts(context, spec=spec, stories=stories)

        if context.verbose:
            self.logger.info(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}Extracted Facts:{Colors.END}")
            self.logger.info(facts)

        return {
            "facts": facts
        }
    
    def get_state_schema_entries(self) -> dict[str, dict]:
        return {
            "facts": text_file("facts.txt")
        }
