"""TypedDict state schema for AgentB (Title Writer)."""

from typing import TypedDict


class AgentBState(TypedDict):
    summary: str
    title: str
    text_id: int
    status: str
