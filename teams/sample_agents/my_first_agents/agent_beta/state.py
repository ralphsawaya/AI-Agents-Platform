"""TypedDict state schema for agent_beta (Report Generator)."""

from typing import TypedDict


class BetaState(TypedDict):
    summary: str
    report: str
    title: str
    status: str
