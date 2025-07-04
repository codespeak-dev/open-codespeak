import json
import logging
from typing import Optional
from anthropic.types import ToolParam
from colors import Colors
from data_serializer import text_file
from phase_manager import State, Phase, Context
from with_step import with_step
from fileutils import load_prompt_template, format_file_content

SYSTEM_PROMPT = "You are a senior web developer who specialized in Django."

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

def extract_layouts(context: Context, spec: str, stories: str, 
                   spec_diff: Optional[str] = None, old_layouts: Optional[list[dict]] = None) -> list[dict]:

    with with_step("Planning layouts..."):
        if spec_diff:
            user_prompt = load_prompt_template("extract_layouts",
                                             spec=spec, spec_diff=spec_diff,
                                             stories=stories, old_layouts=old_layouts)
        else:
            user_prompt = load_prompt_template("extract_layouts",
                                             spec=spec, stories=stories)

        message = context.anthropic_client.create(
            model="claude-3-7-sonnet-latest",
            max_tokens=8192,
            temperature=1,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            thinking={
                "type": "enabled",
                "budget_tokens": 4000
            },
            tools=LAYOUT_TOOLS_SCHEMA
        )

        layouts_data = []
        if hasattr(message, 'content'):
            for content_block in message.content:
                if hasattr(content_block, 'type') and content_block.type == 'tool_use':
                    if hasattr(content_block, 'name') and content_block.name == 'layouts':
                        if hasattr(content_block, 'input') and isinstance(content_block.input, dict):
                            layouts_data = content_block.input.get('layouts', [])
                        break

        return layouts_data

class ExtractLayouts(Phase):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__class__.__qualname__)

    def run(self, state: State, context: Context) -> dict:
        spec_diff = state.get("spec_diff")
        spec = state["spec"]
        
        stories = state.get("stories")
        if not stories:
            raise ValueError("No stories found")

        if spec_diff:
            old_layouts = state.get("layouts")
            if not old_layouts:
                raise ValueError("No layouts found")
            
            spec, _ = format_file_content(spec, offset=None, limit=None, truncate_line=None)
            
            layouts = extract_layouts(context, spec=spec, stories=stories,
                                    spec_diff=spec_diff, old_layouts=old_layouts)
        else:
            layouts = extract_layouts(context, spec=spec, stories=stories)

        if context.verbose:
            self.logger.info(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}Planned Layouts:{Colors.END}")
            self.logger.info(json.dumps(layouts, indent=2))
        else:
            layout_count = len(layouts)
            self.logger.info(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}Planned {layout_count} layouts{Colors.END}")

        return {
            "layouts": layouts
        }
