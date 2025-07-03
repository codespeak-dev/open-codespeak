from dataclasses import dataclass
from jinja2 import Template

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
    with open(template_path, "r") as f:
        template = Template(f.read())
        return template.render(**kwargs)
