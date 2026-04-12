"""Orchestrator state schemas for the trip agent team."""

from typing import Any, TypedDict


class TripSearchState(TypedDict):
    query: str
    thread_id: str
    chat_history: list[dict[str, str]]
    is_search: bool
    nonsearch_reply: str
    flight_filters: dict[str, Any]
    hotel_filters: dict[str, Any]
    car_filters: dict[str, Any]
    flight_results: list[dict[str, Any]]
    hotel_results: list[dict[str, Any]]
    car_results: list[dict[str, Any]]
    error: str


class TripReserveState(TypedDict):
    thread_id: str
    selected_flight: dict[str, Any]
    selected_hotel: dict[str, Any]
    selected_car: dict[str, Any]
    trip_dates: dict[str, str]
    reservation: dict[str, Any]
    status: str
