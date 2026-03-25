"""TypedDict state schema for the Lead Qualifier agent."""

from typing import TypedDict


class LeadQualifierState(TypedDict):
    new_leads: list[dict]
    qualified_leads: list[dict]
    invalid_leads: list[dict]
    qualified_count: int
    scripts_generated: int
    status: str
