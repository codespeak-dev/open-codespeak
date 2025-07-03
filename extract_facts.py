import logging
from colors import Colors
from data_serializer import text_file
from phase_manager import State, Phase, Context
from with_step import with_streaming_step

SYSTEM_PROMPT = """Given a spec and a list of user stories, extract the general facts about the project.
Include things like project name and conventions.
We are only looking for facts that are common across all the user stories and relevant to all of the project, not specific to any one story or a feature.
Return a list of facts in the following format:
- ...
- ...
- ...
"""

def extract_facts(stories: str, spec: str, context: Context) -> str:

    with with_streaming_step("Extracting general facts...") as (input_tokens, output_tokens):
        content = f"<spec>\n{spec}\n</spec>\n<stories>\n{stories}\n</stories>"

        input_tokens[0] = len(content.split()) + len(SYSTEM_PROMPT.split())

        logging.getLogger(ExtractFacts.__class__.__qualname__).info(content)

        response_text = ""
        with context.anthropic_client.stream(
            model="claude-3-7-sonnet-latest",
            max_tokens=16000,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": content
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
        stories = state.get("stories", "")
        spec = state["spec"]

        verbose = context.verbose if context else False

        facts = extract_facts(stories, spec, context)

        if verbose:
            self.logger.info(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}Extracted Facts:{Colors.END}")
            self.logger.info(facts)

        return {
            "facts": facts
        }
    
    def get_state_schema_entries(self) -> dict[str, dict]:
        return {
            "facts": text_file("facts.txt")
        }
