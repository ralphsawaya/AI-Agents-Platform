"""Centralized prompt loader for trip agents.

Loads prompt templates from shared/prompts/ text files and supports
variable substitution using {{variable}} placeholders.
"""

import os
import re

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")
_cache: dict[str, str] = {}


def load_prompt(name: str, **variables: str) -> str:
    """Load a prompt template by name and substitute variables.

    Args:
        name: Filename without extension (e.g. "query_parser_system").
        **variables: Key-value pairs to substitute for {{key}} placeholders.

    Returns:
        The rendered prompt string.
    """
    if name not in _cache:
        path = os.path.join(_PROMPTS_DIR, f"{name}.txt")
        with open(path, "r", encoding="utf-8") as f:
            _cache[name] = f.read()

    template = _cache[name]

    if variables:
        for key, value in variables.items():
            template = template.replace(f"{{{{{key}}}}}", str(value))

    return template


def load_prompt_raw(name: str) -> str:
    """Load a prompt template without variable substitution."""
    return load_prompt(name)
