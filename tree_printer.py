from colors import Colors
from typing import Optional
from contextlib import contextmanager
import logging

class TreePrinter:
    """Utility for printing hierarchical tree-like output"""
    
    def __init__(self):
        self.indent_level = 0
        self.active_sections: list[str] = []
        self.logger = logging.getLogger(__class__.__qualname__)
    
    def _get_indent(self, level: int = 0) -> str:
        """Get indentation string for the current level"""
        base_level = self.indent_level + level
        if base_level == 0:
            return ""
        return "  " * base_level
    
    def _format_message(self, icon: str, message: str, color: str = "") -> str:
        """Format a message with icon and color"""
        colored_icon = f"{color}{icon}{Colors.END}" if color else icon
        return f"{colored_icon} {message}"
    
    def section(self, title: str, color: str = Colors.BRIGHT_CYAN) -> None:
        """Start a new section with a title"""
        indent = self._get_indent()
        colored_title = f"{color}{title}{Colors.END}"
        self.logger.info(f"{indent}⏺ {colored_title}")
        self.active_sections.append(title)
    
    def item(self, icon: str, message: str, color: str = "") -> None:
        """Print an item with custom icon and color"""
        indent = self._get_indent()
        formatted = self._format_message(icon, message, color)
        self.logger.info(f"{indent}  ⎿  {formatted}")
    
    def success(self, message: str) -> None:
        """Print a success item with green checkmark"""
        self.item("✓", message, Colors.BRIGHT_GREEN)
    
    def error(self, message: str) -> None:
        """Print an error item with red X"""
        self.item("✗", message, Colors.BRIGHT_RED)
    
    def info(self, message: str) -> None:
        """Print an info item with blue dot"""
        self.item("•", message, Colors.BRIGHT_BLUE)
    
    def warning(self, message: str) -> None:
        """Print a warning item with yellow triangle"""
        self.item("⚠", message, Colors.BRIGHT_YELLOW)
    
    def progress(self, message: str) -> None:
        """Print a progress item with cyan arrow"""
        self.item("→", message, Colors.BRIGHT_CYAN)
    
    @contextmanager
    def nested(self, title: Optional[str] = None):
        """Context manager for nested sections"""
        if title:
            self.section(title)
        
        self.indent_level += 1
        try:
            yield self
        finally:
            self.indent_level -= 1
            if title and self.active_sections:
                self.active_sections.pop()

# Global instance for convenience
tree = TreePrinter()

# Convenience functions that use the global instance
def tree_section(title: str, color: str = Colors.BRIGHT_CYAN) -> None:
    """Start a new section"""
    tree.section(title, color)

def tree_success(message: str) -> None:
    """Print success item"""
    tree.success(message)

def tree_error(message: str) -> None:
    """Print error item"""
    tree.error(message)

def tree_info(message: str) -> None:
    """Print info item"""
    tree.info(message)

def tree_warning(message: str) -> None:
    """Print warning item"""
    tree.warning(message)

def tree_progress(message: str) -> None:
    """Print progress item"""
    tree.progress(message)

def tree_item(icon: str, message: str, color: str = "") -> None:
    """Print custom item"""
    tree.item(icon, message, color)

@contextmanager
def tree_nested(title: Optional[str] = None):
    """Context manager for nested sections"""
    with tree.nested(title):
        yield tree 