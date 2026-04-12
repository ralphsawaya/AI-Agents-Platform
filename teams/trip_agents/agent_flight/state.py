"""TypedDict state schema for the Flight Search agent."""

from typing import TypedDict


class FlightSearchState(TypedDict):
    query: str
    query_embedding: list
    filters: dict
    results: list
    status: str
