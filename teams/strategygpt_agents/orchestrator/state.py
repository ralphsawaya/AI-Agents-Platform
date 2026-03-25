"""Shared orchestrator state that flows between StrategyGPT agents."""

from typing import TypedDict


class SourcingPipelineState(TypedDict):
    city: str
    categories: list[str]
    min_reviews: int
    min_rating: float
    max_leads: int
    raw_places: list[dict]
    filtered_leads: list[dict]
    stored_count: int
    qualified_count: int
    scripts_generated: int
    current_agent: str
    status: str


class OutreachPipelineState(TypedDict):
    lead_ids: list[str] | str
    batch_size: int
    leads_to_call: list[dict]
    call_results: list[dict]
    interested_count: int
    not_interested_count: int
    no_answer_count: int
    current_agent: str
    status: str


class FullPipelineState(TypedDict):
    city: str
    categories: list[str]
    min_reviews: int
    min_rating: float
    max_leads: int
    lead_ids: list[str] | str
    batch_size: int
    raw_places: list[dict]
    filtered_leads: list[dict]
    stored_count: int
    qualified_count: int
    scripts_generated: int
    leads_to_call: list[dict]
    call_results: list[dict]
    interested_count: int
    not_interested_count: int
    no_answer_count: int
    current_agent: str
    status: str
