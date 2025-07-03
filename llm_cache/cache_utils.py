class SubstringBasedSanitizer:
    def __init__(self, substrings: list[tuple[str, str]]):
        """
        substrings is a list of tuples of substrings to replace with their values.
        values must be distinct from each other.
        The substrings are replaced in the order they are given.
        """
        # check that substrings are distinct from each other
        replacements = set(s for _, s in substrings)
        if len(replacements) != len(substrings):
            raise ValueError("Substrings must be distinct from each other")
        
        self.substrings = substrings

    def sanitize_str(self, text: str) -> str:
        return self._perform_replacement(text, self.substrings)

    def desanitize_str(self, text: str) -> str:
        return self._perform_replacement(text, reversed([(b, a) for a, b in self.substrings]))

    def _perform_replacement(self, text, substrings):
        for pattern, replacement in substrings:
            text = text.replace(pattern, replacement)
        return text
