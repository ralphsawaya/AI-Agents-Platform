"""TypedDict state schema for the Car Rental Search agent."""

from typing import TypedDict


class CarSearchState(TypedDict):
    query: str
    query_embedding: list
    filters: dict
    results: list
    status: str
