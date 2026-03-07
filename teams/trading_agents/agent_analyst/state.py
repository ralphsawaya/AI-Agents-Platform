"""TypedDict state schema for the Analyst agent."""

from typing import TypedDict


class AnalystState(TypedDict):
    ohlcv_4h: list
    ohlcv_1h: list
    indicators: dict
    regime: str
    confidence: float
    reasoning: str
    status: str
