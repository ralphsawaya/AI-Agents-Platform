"""TypedDict state schema for agent_alpha (Summarizer)."""

from typing import TypedDict


class AlphaState(TypedDict):
    input_text: str
    summary: str
    word_count: int
    status: str
