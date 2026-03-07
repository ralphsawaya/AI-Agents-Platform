"""TypedDict state schema for the Strategist agent."""

from typing import TypedDict


class StrategistState(TypedDict):
    regime: str
    confidence: float
    indicators: dict
    strategy_candidates: list
    selected_strategy: str
    reasoning: str
    status: str
