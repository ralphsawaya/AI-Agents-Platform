"""Orchestrator state schemas for the trip agent team."""

from typing import Any, TypedDict


class TripAgentState(TypedDict):
    query: str
    thread_id: str
    chat_history: list[dict[str, str]]
    mode: str
    reservation_id: str
    reservation: dict[str, Any]
    plan: dict[str, Any]
    intent: str
    reply: str
    tool_results: list[dict[str, Any]]
    search_results: dict[str, Any]
    proposed_bundle: dict[str, Any] | None
    tool_trace: list[dict[str, Any]]
    replan_count: int
    modify_category: str
    error: str


class TripReserveState(TypedDict):
    thread_id: str
    selected_flight: dict[str, Any]
    selected_hotel: dict[str, Any]
    selected_car: dict[str, Any]
    trip_dates: dict[str, str]
    reservation: dict[str, Any]
    status: str
