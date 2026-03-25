"""TypedDict state schema for the Lead Sourcer agent."""

from typing import TypedDict


class LeadSourcerState(TypedDict):
    city: str
    categories: list[str]
    min_reviews: int
    min_rating: float
    max_leads: int
    raw_places: list[dict]
    filtered_leads: list[dict]
    stored_count: int
    status: str
