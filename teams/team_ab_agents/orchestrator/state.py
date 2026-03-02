"""Shared orchestrator state that flows between AgentA and AgentB."""

from typing import TypedDict


class OrchestratorState(TypedDict):
    input_text: str
    summary: str
    title: str
    text_id: int
    current_agent: str
    status: str
