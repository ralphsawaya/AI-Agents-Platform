"""Text processing tools for agent_alpha."""

from langchain_core.tools import tool


@tool
def count_words(text: str) -> int:
    """Count the number of words in a text."""
    return len(text.split())


@tool
def truncate_text(text: str, max_words: int = 500) -> str:
    """Truncate text to a maximum number of words."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "…"
