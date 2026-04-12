"""TypedDict state schema for the Hotel Search agent."""

from typing import TypedDict


class HotelSearchState(TypedDict):
    query: str
    query_embedding: list
    filters: dict
    results: list
    status: str
