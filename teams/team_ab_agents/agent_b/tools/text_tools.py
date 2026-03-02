"""Text processing tools for AgentB."""

from langchain_core.tools import tool


@tool
def clean_title(title: str) -> str:
    """Strip quotes and whitespace from a generated title."""
    return title.strip().strip('"').strip("'")
