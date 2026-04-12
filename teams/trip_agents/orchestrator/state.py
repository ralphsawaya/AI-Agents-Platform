"""Shared orchestrator state that flows between trip agents."""

from typing import TypedDict


class TripSearchState(TypedDict):
    query: str
    thread_id: str
    chat_history: list
    is_search: bool
    nonsearch_reply: str
    flight_filters: dict
    hotel_filters: dict
    car_filters: dict
    flight_results: list
    hotel_results: list
    car_results: list
    error: str


class TripReserveState(TypedDict):
    thread_id: str
    selected_flight: dict
    selected_hotel: dict
    selected_car: dict
    trip_dates: dict
    reservation: dict
    status: str


class TripModifySearchState(TypedDict):
    query: str
    thread_id: str
    reservation_id: str
    category: str
    filters: dict
    results: list
    error: str
