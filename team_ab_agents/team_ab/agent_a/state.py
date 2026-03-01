"""TypedDict state schema for AgentA (Summarizer)."""

from typing import TypedDict


class AgentAState(TypedDict):
    input_text: str
    summary: str
    text_id: int
    word_count: int
    status: str
