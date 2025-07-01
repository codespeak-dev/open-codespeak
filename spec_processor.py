class SpecProcessor:
    """Processes specification files by removing comment lines and other transformations."""
    
    def __init__(self):
        pass
    
    def process(self, spec_content: str) -> str:
        """
        Process the specification content by removing lines that start with //.
        Lines with leading whitespace followed by // are also removed.
        
        Args:
            spec_content (str): The raw specification content
            
        Returns:
            str: The processed specification content
        """
        lines = spec_content.split('\n')
        processed_lines = []
        
        for line in lines:
            # Strip leading whitespace and check if line starts with //
            stripped_line = line.lstrip()
            if not stripped_line.startswith('//'):
                processed_lines.append(line)
        
        return '\n'.join(processed_lines) 