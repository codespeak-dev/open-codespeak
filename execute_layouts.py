import anthropic
from anthropic.types import ToolParam
import os
import json
import time
from typing import cast, Optional
from colors import Colors
from phase_manager import State, Phase, Context

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
You are a Django developer tasked with implementing layout templates.

Your task is to implement each layout by creating HTML template files in the templates directory.

For each layout, parse the name, description and style requirements.
Create clean, functional Django template files that follow best practices and use Tailwind CSS.

Follow modern web design principles and create responsive layouts.

## Available Tools

You have access to the write_file tool to create template files.

### write_file
Write content to a new file

Input Schema:
```json
{
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
```

## Guidelines

1. Create template files in the templates/ directory
2. Use Tailwind CSS for styling (connect from CDN)
3. Follow Django template best practices
4. Create responsive, modern layouts
5. Use semantic HTML structure
"""

class LayoutImplementationAgent:
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.anthropic_client = anthropic.Anthropic()
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
        print(f"{Colors.BRIGHT_GREEN}✓{Colors.END} Created {file_path}")
        return True

    def run_anthropic_conversation(self, messages: list) -> dict:
        """Run a streaming conversation with Claude until completion"""
        output_tokens = 0
        total_api_duration = 0.0

        # Continue conversation until no more tool calls
        while True:
            # Track API call duration
            api_start_time = time.time()

            with self.anthropic_client.messages.stream(
                model="claude-3-7-sonnet-latest", 
                max_tokens=10000,
                temperature=0,
                system=LAYOUT_IMPLEMENTATION_SYSTEM_PROMPT,
                tools=LAYOUT_TOOLS_DEFINITIONS,
                messages=messages
            ) as stream:
                # Get the final message with all content blocks
                final_message = stream.get_final_message()

            api_end_time = time.time()
            api_call_duration = api_end_time - api_start_time
            total_api_duration += api_call_duration
            output_tokens += final_message.usage.output_tokens

            # Add assistant message to conversation  
            messages.append({
                "role": "assistant", 
                "content": final_message.content
            })

            # Check if there are tool calls to execute
            tool_calls = [block for block in final_message.content if hasattr(block, 'type') and block.type == "tool_use"]

            if not tool_calls:
                break

            # Execute tool calls and collect results
            tool_results = []
            for tool_call in tool_calls:
                # Only handle write_file tool
                if tool_call.name == "write_file":
                    tool_input = cast(dict, tool_call.input)
                    self.write_file(tool_input["file_path"], tool_input["content"])

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": json.dumps({"success": True})
                })

            # Add tool results to conversation
            messages.append({
                "role": "user",
                "content": tool_results
            })

        return {
            "total_output_tokens": output_tokens,
            "total_api_duration": total_api_duration
        }

    def implement_layout(self, layout_text: str):
        """Implement a layout by creating template files"""
        # Create prompt for implementation
        prompt = f"<layout>{layout_text}</layout>"
        messages = [{"role": "user", "content": prompt}]
        
        # Run the streaming conversation
        result = self.run_anthropic_conversation(messages)
        return result

class ExecuteLayouts(Phase):
    def run(self, state: State, context: Optional[Context] = None) -> dict:
        layouts = state["layouts"]
        project_path = state["project_path"]

        # Parse layouts by splitting on "Layout:" markers
        layout_sections = layouts.split("Layout:")
        layout_sections = [section.strip() for section in layout_sections[1:] if section.strip()]
        
        print(f"{Colors.BRIGHT_CYAN}Implementing {len(layout_sections)} layouts...{Colors.END}")

        # Create implementation agent (Anthropic only)
        agent = LayoutImplementationAgent(project_path)
        total_api_duration = 0.0

        # Process each layout
        for i, layout in enumerate(layout_sections):
            print(f"{Colors.BRIGHT_YELLOW}[{i+1}/{len(layout_sections)}]{Colors.END} Processing layout...")

            # Implement the layout
            result = agent.implement_layout(layout)
            layout_api_duration = result.get('total_api_duration', 0)
            total_api_duration += layout_api_duration

        print(f"\n{Colors.BRIGHT_GREEN}✓ Completed{Colors.END} - Created {len(agent.files_created)} files")

        return {
            "provider": "anthropic",
            "total_api_duration": total_api_duration
        }
    
    def get_state_schema_entries(self) -> dict:
        return {} 