from typing import Dict, Optional
import anthropic
import json
from anthropic.types import ToolParam
from colors import Colors
from data_serializer import text_file
from phase_manager import State, Phase, Context
from with_step import with_streaming_step

PLAN_LAYOUTS_SYSTEM_PROMPT = """You are a senior web developer who specialized in Django.
As input you have a list of user stories and screens that need to be implemented in an app.
Return a list of base layouts that will be used to implement the app."""

# Tool definitions constant
LAYOUT_TOOLS_SCHEMA: list[ToolParam] = [
    ToolParam(
        name="layouts",
        description="Builds all detected layouts",
        input_schema={
            "type": "object",
            "properties": {
                "technologies": {
                    "type": "string",
                    "description": "Outlines any general guidelines around the choice of UX technologies"
                },
                "layouts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "The name of layout. It will be used for filename. Whenever possible, use a single word. If not possible, use two words separated by underscore"
                            },
                            "description": {
                                "type": "string",
                                "description": "Description of things and features and user scenarios that this layout will be used for"
                            },
                            "style": {
                                "type": "string",
                                "description": "Brief description of the style of this layout and how it should be seen by a user"
                            }
                        },
                        "required": [
                            "name",
                            "description",
                            "style"
                        ]
                    }
                }
            }
        }
    )
]

def extract_layouts_with_claude(stories: str, spec: str) -> list[dict]:
    client = anthropic.Anthropic()

    with with_streaming_step("Planning layouts...") as (input_tokens, output_tokens):
        content = f"<spec>\n{spec}\n</spec>\n<stories>\n{stories}\n</stories>"
        
        input_tokens[0] = len(content.split()) + len(PLAN_LAYOUTS_SYSTEM_PROMPT.split())

        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=8192,
            temperature=1,
            system=PLAN_LAYOUTS_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": content
                }
            ],
            tools=LAYOUT_TOOLS_SCHEMA
        )
        
        # Calculate output tokens
        if hasattr(message, 'content'):
            for content_block in message.content:
                if hasattr(content_block, 'type') and content_block.type == 'text':
                    output_tokens[0] += len(content_block.text.split())
        
        # Extract layouts from tool use
        layouts_data = []
        if hasattr(message, 'content'):
            for content_block in message.content:
                if hasattr(content_block, 'type') and content_block.type == 'tool_use':
                    if hasattr(content_block, 'name') and content_block.name == 'layouts':
                        if hasattr(content_block, 'input') and isinstance(content_block.input, dict):
                            layouts_data = content_block.input.get('layouts', [])
                        break

        return layouts_data

        # return result.strip()

class ExtractLayouts(Phase):
    def run(self, state: State, context: Optional[Context] = None) -> dict:
        stories = state.get("stories", "")
        spec = state["spec"]
        verbose = context.verbose if context else False

        layouts = extract_layouts_with_claude(stories, spec)

        if verbose:
            print(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}Planned Layouts:{Colors.END}")
            print(json.dumps(layouts, indent=2))
        else:
            layout_count = len(layouts)
            print(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}Planned {layout_count} layouts{Colors.END}")

        return {
            "layouts": layouts
        }
