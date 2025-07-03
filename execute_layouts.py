import asyncio
from anthropic import AsyncAnthropic
from anthropic.types import ToolParam
import os
import json
from typing import cast, Optional
from colors import Colors
from phase_manager import State, Phase, Context
from tree_printer import tree_section, tree_success, tree_error

# Tool definitions constant - only write_file
LAYOUT_TOOLS_DEFINITIONS: list[ToolParam] = [
    ToolParam(
        name="write_file",
        description="Write content to a new file",
        input_schema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to create"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file"
                }
            },
            "required": ["file_path", "content"]
        }
    )
]

LAYOUT_IMPLEMENTATION_SYSTEM_PROMPT = """
You are a Django developer tasked with implementing a layout template.
Your task is to implement a layout by creating HTML template file in the templates/layouts/ directory.
You must respect facts provided to you about the app.

## Guidelines

1. Create exactly one template file in the templates/layouts/ directory
2. Follow Django template best practices
3. Create responsive, modern layout
4. Use semantic HTML structure
"""

class LayoutImplementationAgent:
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.anthropic_client = AsyncAnthropic()
        self.files_created = []

    def write_file(self, file_path: str, content: str):
        """Write content to a new file"""
        full_path = os.path.join(self.project_path, file_path) if not os.path.isabs(file_path) else file_path
        
        dir_path = os.path.dirname(full_path)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        self.files_created.append(file_path)
        tree_success(f"Created {file_path}")
        return True

    async def run_anthropic_conversation(self, messages: list):
        """Run a streaming conversation with Claude until completion"""
        tool_use_count = 0

        while True:
            async with self.anthropic_client.messages.stream(
                model="claude-3-7-sonnet-latest", 
                max_tokens=10000,
                temperature=0,
                system=LAYOUT_IMPLEMENTATION_SYSTEM_PROMPT,
                tools=LAYOUT_TOOLS_DEFINITIONS,
                messages=messages
            ) as stream:
                final_message = await stream.get_final_message()

            messages.append({
                "role": "assistant", 
                "content": final_message.content
            })

            tool_calls = [block for block in final_message.content if hasattr(block, 'type') and block.type == "tool_use"]

            if not tool_calls:
                break

            if tool_use_count + len(tool_calls) > 1:
                raise ValueError(f"Layout attempted to use {tool_use_count + len(tool_calls)} tools, but only 1 is allowed per layout")

            tool_results = []
            for tool_call in tool_calls:
                if tool_call.name == "write_file":
                    tool_input = cast(dict, tool_call.input)
                    self.write_file(tool_input["file_path"], tool_input["content"])
                    tool_use_count += 1
                else:
                    raise ValueError(f"Unknown tool: {tool_call.name}")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": json.dumps({"success": True})
                })

            messages.append({
                "role": "user",
                "content": tool_results
            })

    async def implement_layout(self, layout: dict, facts: str):
        """Implement a layout by creating template files"""
        layout_name = layout["name"]
        layout_description = layout["description"]
        layout_style = layout["style"]

        prompt = f"""<facts>{facts}</facts>
<layout_name>{layout_name}</layout_name>
<layout_description>{layout_description}</layout_description>
<layout_style>{layout_style}</layout_style>

Create a template file named templates/layouts/{layout_name}.html"""

        messages = [{"role": "user", "content": prompt}]

        await self.run_anthropic_conversation(messages)

class ExecuteLayouts(Phase):
    def run(self, state: State, context: Optional[Context] = None) -> dict:
        layouts = state["layouts"]
        facts = state["facts"]
        project_path = state["project_path"]

        tree_section("Generate layouts")

        agent = LayoutImplementationAgent(project_path)
        async def process_layouts_async():
            tasks = [
                agent.implement_layout(layout, facts)
                for layout in layouts
            ]

            await asyncio.gather(*tasks)

            tree_success(f"All {len(layouts)} layouts completed successfully")

        try:
            asyncio.run(process_layouts_async())
            tree_success(f"Process completed - Created {len(agent.files_created)} files")
        except Exception as e:
            tree_error(f"Process failed - {e}")
            raise

        return {}
