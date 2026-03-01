"""Shared orchestrator state that flows between agents."""

from typing import TypedDict


class OrchestratorState(TypedDict):
    input_text: str
    summary: str
    report: str
    current_agent: str
    status: str
