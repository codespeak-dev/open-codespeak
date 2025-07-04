import os
from dataclasses import dataclass
from typing import cast
from jinja2 import Template, Environment, FileSystemLoader
from anthropic.types import ToolParam

@dataclass
class FileMetadata:
    lines_processed: int
    truncated: bool
    start_line: int
    end_line: int
    total_lines: int


def format_file_content(content: str, offset: int | None = None, limit: int | None = None, truncate_line: int | None = 2000) -> tuple[str, FileMetadata]:
    """
    Format file content with line numbers and optional truncation.
    
    Args:
        content: The file content to format
        offset: Optional starting line number (1-based)
        limit: Optional maximum number of lines to format
        truncate_line: Optional max line length before truncation (None = no truncation)
    
    Returns:
        Tuple of (formatted_content, FileMetadata)
        where FileMetadata contains: lines_processed, truncated, start_line, end_line, total_lines
    """
    lines = []
    truncated = False
    
    # Process lines for display
    all_lines = content.splitlines()
    
    # Determine which lines to process
    start_line = (offset - 1) if offset is not None else 0
    end_line = len(all_lines)
    
    if limit is not None and offset is not None:
        end_line = min(len(all_lines), start_line + limit)
    elif limit is not None and offset is None:
        end_line = min(len(all_lines), limit)
    
    for i in range(start_line, end_line):
        line = all_lines[i]
        line_number = i + 1
        
        # Truncate long lines if specified
        line_content = line
        if truncate_line is not None and len(line_content) > truncate_line:
            line_content = line_content[:truncate_line] + '... (truncated)'
        
        # Format with line numbers (cat -n style)
        formatted_line = f"{line_number}\t{line_content}"
        lines.append(formatted_line)
    
    # Check if we truncated due to limit
    if limit is not None and len(all_lines) > end_line:
        truncated = True
    
    display_content = '\n'.join(lines)
    
    metadata = FileMetadata(
        lines_processed=len(lines),
        truncated=truncated,
        start_line=start_line + 1,  # Convert back to 1-based
        end_line=end_line,
        total_lines=len(all_lines)
    )
    
    return display_content, metadata

def load_template(template_path: str, **kwargs) -> str:
    """
    Load a Jinja2 template file and render it with provided kwargs.

    Args:
        template_path: Path to the .j2 template file
        **kwargs: Arbitrary keyword arguments to pass to the template

    Returns:
        Rendered template content as string
    """
    # Get the directory and filename for the template
    template_dir = os.path.dirname(template_path)
    template_name = os.path.basename(template_path)

    # Create a Jinja2 environment with FileSystemLoader
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template(template_name)

    return template.render(**kwargs)


def load_prompt_template(template_name: str, **kwargs) -> str:
    """
    Load a Jinja2 template from the prompts directory and render it with provided kwargs.

    Args:
        template_name: Name of the template file without extension (e.g., "extract_entities")
        **kwargs: Arbitrary keyword arguments to pass to the template

    Returns:
        Rendered template content as string
    """
    template_path = f"prompts/{template_name}.j2"
    return load_template(template_path, **kwargs)


class LLMFileGenerator:
    """
    Handles the common pattern of LLM calls that expect a single file write operation.
    Validates that only one tool call is made and writes to the expected file path.
    """
    
    def __init__(self, model: str = "claude-3-7-sonnet-latest", max_tokens: int = 8192, temperature: float = 0):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.tools = [
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
    
    async def generate_and_write_async(self, anthropic_client, *, system: str, messages: list, 
                                     expected_file_path: str, output_file_path: str, 
                                     max_tokens: int | None = None, temperature: float | None = None) -> str:
        """
        Async version of generate_and_write for use with AsyncAnthropic clients.
        """
        message = await anthropic_client.async_create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature or self.temperature,
            system=system,
            tools=self.tools,
            messages=messages
        )
        
        tool_calls = [block for block in message.content if hasattr(block, 'type') and block.type == "tool_use"]
        
        if len(tool_calls) > 1:
            raise ValueError("Only one tool call is allowed, got: " + str(tool_calls))
        
        for tool_call in tool_calls:
            if tool_call.name == "write_file":
                tool_input = cast(dict, tool_call.input)
                if tool_input["file_path"] == expected_file_path:
                    # Create directory if it doesn't exist
                    dir_path = os.path.dirname(output_file_path)
                    if not os.path.exists(dir_path):
                        os.makedirs(dir_path, exist_ok=True)
                    
                    with open(output_file_path, "w", encoding="utf-8") as f:
                        f.write(tool_input["content"])
                else:
                    raise ValueError(f"Only writing to {expected_file_path} is supported, got: {tool_input['file_path']}")
            else:
                raise ValueError(f"Unknown tool: {tool_call.name}")
        
        return output_file_path

    def generate_and_write(self, anthropic_client, *, system: str, messages: list, 
                          expected_file_path: str, output_file_path: str, 
                          max_tokens: int | None = None, temperature: float | None = None) -> str:
        """
        Generate content using LLM and write to a single file.
        
        Args:
            anthropic_client: The Anthropic client instance
            system: System prompt for the LLM
            messages: List of messages for the conversation
            expected_file_path: The file path the LLM should specify in its tool call
            output_file_path: The actual file path to write to
            max_tokens: Override max_tokens (optional)  
            temperature: Override temperature (optional)
            
        Returns:
            The output file path
            
        Raises:
            ValueError: If more than one tool call is made or unexpected file path is used
        """
        message = anthropic_client.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature or self.temperature,
            system=system,
            tools=self.tools,
            messages=messages
        )
        
        tool_calls = [block for block in message.content if hasattr(block, 'type') and block.type == "tool_use"]
        
        if len(tool_calls) > 1:
            raise ValueError("Only one tool call is allowed, got: " + str(tool_calls))
        
        for tool_call in tool_calls:
            if tool_call.name == "write_file":
                tool_input = cast(dict, tool_call.input)
                if tool_input["file_path"] == expected_file_path:
                    with open(output_file_path, "w", encoding="utf-8") as f:
                        f.write(tool_input["content"])
                else:
                    raise ValueError(f"Only writing to {expected_file_path} is supported, got: {tool_input['file_path']}")
            else:
                raise ValueError(f"Unknown tool: {tool_call.name}")
        
        return output_file_path
