#!/usr/bin/env python3

import dotenv

dotenv.load_dotenv()

import sys
import os
import re
import argparse
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("Error: anthropic library not installed. Run: pip install anthropic")
    sys.exit(1)

# ANSI color codes for terminal output
FOREGROUND_COLORS = {
    'green': '\033[32m',        # Bright green text
    'red': '\033[91m',          # Bright red text
    'yellow': '\033[93m',       # Bright yellow text
    'gray': '\033[90m',         # Dark gray text
    'blue': '\033[94m',         # Bright blue text
    'purple': '\033[95m',       # Bright magenta text
    'orange': '\033[38;5;208m', # Orange text
    'reset': '\033[0m'          # Reset to default
}

BACKGROUND_COLORS = {
    'green': '\033[42m\033[30m',        # Green background, black text
    'red': '\033[41m\033[97m',          # Red background, bright white text
    'yellow': '\033[43m\033[30m',       # Yellow background, black text
    'gray': '\033[100m\033[97m',        # Gray background, bright white text
    'blue': '\033[44m\033[97m',         # Blue background, bright white text
    'purple': '\033[45m\033[97m',       # Purple background, bright white text
    'orange': '\033[48;5;208m\033[30m', # Orange background, black text
    'reset': '\033[0m'                  # Reset to default
}

def read_file(file_path):
    """Read the specification file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)

def get_claude_response(spec_content):
    """Send specification to Claude for highlighting."""
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        print("Get your API key from: https://console.anthropic.com/")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""I have a specification for developing a website.
I'd like to semantically highlight different parts of the spec using Data Flow Direction.

Please highlight the specification using these XML-style tags:
- <green></green> for Input/Creation - where users create or input data
- <blue></blue> for Output/Display - information presentation  
- <orange></orange> for Interaction/Action - user decisions & actions
- <purple></purple> for System Processing - behind-the-scenes operations

Return ONLY the highlighted specification text with the tags, no explanations or additional text.

<spec>
{spec_content}
</spec>"""

    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        print(f"Error calling Claude API: {e}")
        sys.exit(1)

def apply_terminal_colors(text, color_mode='fg'):
    """Replace XML color tags with ANSI terminal colors and handle line breaks."""
    # Select color palette based on mode
    colors = FOREGROUND_COLORS if color_mode == 'fg' else BACKGROUND_COLORS

    # Define tag to color mapping
    tag_colors = {
        'green': 'green',
        'red': 'red', 
        'yellow': 'yellow',
        'gray': 'gray',
        'blue': 'blue',
        'purple': 'purple',
        'orange': 'orange'
    }

    # Split text into lines for processing
    lines = text.split('\n')
    processed_lines = []

    for line in lines:
        processed_line = line

        # Replace opening and closing tags within each line
        for tag, color in tag_colors.items():
            # Replace opening tags
            processed_line = re.sub(f'<{tag}>', colors[color], processed_line)
            # Replace closing tags
            processed_line = re.sub(f'</{tag}>', colors['reset'], processed_line)

        processed_lines.append(processed_line)

    # Now handle multi-line color spans
    final_lines = []
    current_color = None

    for line in processed_lines:
        # Check if line starts a color (contains color code but not at start due to preceding reset)
        line_starts_color = None
        line_ends_with_reset = line.endswith(colors['reset'])

        # Find which color this line contains
        for color_name, color_code in colors.items():
            if color_name != 'reset' and color_code in line:
                line_starts_color = color_code
                break

        # If we're continuing a color from previous line, start this line with that color
        if current_color and not line_starts_color:
            line = current_color + line

        # If this line ends with a reset, we're no longer in a color span
        if line_ends_with_reset:
            current_color = None
        # If this line has color but doesn't end with reset, we need to continue the color
        elif line_starts_color:
            current_color = line_starts_color
            # Add reset at end of line if it doesn't already have one
            if not line.endswith(colors['reset']):
                line = line + colors['reset']

        final_lines.append(line)

    return '\n'.join(final_lines)

def print_legend(color_mode='fg'):
    """Print a color legend for the highlighting."""
    colors = FOREGROUND_COLORS if color_mode == 'fg' else BACKGROUND_COLORS
    mode_name = "FOREGROUND" if color_mode == 'fg' else "BACKGROUND"

    print("\n" + "="*60)
    print(f"DATA FLOW DIRECTION HIGHLIGHTING LEGEND ({mode_name} MODE)")
    print("="*60)
    print(f"{colors['green']}Input/Creation{colors['reset']} - Users create or input data")
    print(f"{colors['blue']}Output/Display{colors['reset']} - Information presentation") 
    print(f"{colors['orange']}Interaction/Action{colors['reset']} - User decisions & actions")
    print(f"{colors['purple']}System Processing{colors['reset']} - Behind-the-scenes operations")
    print("="*60 + "\n")

def main():
    parser = argparse.ArgumentParser(
        description='Highlight specification files using Claude API with Data Flow Direction categories',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python highlight_spec.py spec.md                    # Use foreground colors (default)
  python highlight_spec.py --mode fg spec.md          # Use foreground colors
  python highlight_spec.py --mode bg spec.md          # Use background colors
        """
    )

    parser.add_argument('file_path', help='Path to the specification file to highlight')
    parser.add_argument('--mode', choices=['fg', 'bg'], default='fg',
                       help='Color mode: fg=foreground colors, bg=background colors (default: fg)')

    args = parser.parse_args()

    # Validate file exists
    if not Path(args.file_path).exists():
        print(f"Error: File '{args.file_path}' does not exist")
        sys.exit(1)

    print(f"Reading specification from: {args.file_path}")
    print(f"Using color mode: {'foreground' if args.mode == 'fg' else 'background'}")
    spec_content = read_file(args.file_path)

    print("Sending to Claude for highlighting...")
    highlighted_spec = get_claude_response(spec_content)

    print("Applying terminal colors...")
    colored_output = apply_terminal_colors(highlighted_spec, args.mode)

    # Print legend
    print_legend(args.mode)

    # Print the highlighted specification
    print(colored_output)

    # Reset colors at the end
    colors = FOREGROUND_COLORS if args.mode == 'fg' else BACKGROUND_COLORS
    print(colors['reset'])

if __name__ == "__main__":
    main()
