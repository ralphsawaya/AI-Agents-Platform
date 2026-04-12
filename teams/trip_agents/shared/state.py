"""Shared state schemas for search sub-agents.

All three sub-agents (flight, hotel, car) use the same state shape,
so we define it once here to avoid duplication.
"""

from typing import Any, TypedDict


class SearchAgentState(TypedDict):
    query: str
    query_embedding: list[float]
    filters: dict[str, Any]
    results: list[dict[str, Any]]
    status: str
