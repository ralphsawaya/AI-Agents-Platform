"""Basic tests for trip agent pipeline components."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_shared_config_imports():
    from shared.config import (
        FLIGHTS_COLLECTION, HOTELS_COLLECTION, CARS_COLLECTION,
        VOYAGE_MODEL, VOYAGE_EMBED_DIM,
    )
    assert FLIGHTS_COLLECTION == "trip_flights"
    assert HOTELS_COLLECTION == "trip_hotels"
    assert CARS_COLLECTION == "trip_cars"
    assert VOYAGE_MODEL == "voyage-3-lite"
    assert VOYAGE_EMBED_DIM == 512


def test_state_schemas():
    from orchestrator.state import TripAgentState, TripReserveState
    assert "query" in TripAgentState.__annotations__
    assert "search_results" in TripAgentState.__annotations__
    assert "modify_category" in TripAgentState.__annotations__
    assert "tool_trace" in TripAgentState.__annotations__
    assert "selected_flight" in TripReserveState.__annotations__
    assert "reservation" in TripReserveState.__annotations__


def test_subagent_states():
    from agent_flight.state import FlightSearchState
    from agent_hotel.state import HotelSearchState
    from agent_car.state import CarSearchState
    for state_cls in (FlightSearchState, HotelSearchState, CarSearchState):
        assert "query" in state_cls.__annotations__
        assert "query_embedding" in state_cls.__annotations__
        assert "results" in state_cls.__annotations__
        assert "status" in state_cls.__annotations__


def test_utils_load_args():
    os.environ["AGENT_ARGS"] = '{"mode": "search", "prompt": "test"}'
    from shared.utils import load_args
    args = load_args()
    assert args["mode"] == "search"
    assert args["prompt"] == "test"
    os.environ.pop("AGENT_ARGS", None)


def test_hotel_nights_from_trip_dates():
    from shared.utils import hotel_nights_from_trip_dates
    assert hotel_nights_from_trip_dates({}) == 7
    assert hotel_nights_from_trip_dates({"start": "2026-03-01", "end": "2026-03-08"}) == 7
    assert hotel_nights_from_trip_dates({"start": "bad", "end": "2026-03-08"}) == 7


def test_reservation_filter_scopes_agent():
    from shared.atlas import reservation_filter

    filt = reservation_filter("TRIP-20260301-ABCD", agent_id="test-agent-123")
    assert filt["_id"] == "TRIP-20260301-ABCD"
    assert filt["agent_id"] == "test-agent-123"


def test_extract_json_array():
    from shared.json_utils import extract_json_array

    assert extract_json_array('Here: [{"fact": "prefers business class"}]') == [
        {"fact": "prefers business class"}
    ]
    assert extract_json_array("no array here") == []
    assert extract_json_array('[{"a": 1}, {"b": 2}] extra') == [{"a": 1}, {"b": 2}]


def test_filter_cleaners():
    from shared.filters import clean_flight_filters, clean_hotel_filters, clean_car_filters

    assert clean_flight_filters({"destination_city": "Paris", "travel_class": "Business"}) == {
        "destination_city": "Paris", "travel_class": "business",
    }
    assert clean_hotel_filters({"city": "Rome", "stars": 4}) == {"city": "Rome", "stars": 4}
    assert clean_car_filters({"make": "Kia", "category": "invalid"}) == {"make": "Kia"}


def test_search_graph_builds():
    try:
        import langgraph  # noqa: F401
    except ImportError:
        return  # skipped when langgraph not installed (e.g. bare CI host)
    from agent_flight.agent import build_flight_graph
    from agent_hotel.agent import build_hotel_graph
    from agent_car.agent import build_car_graph
    for builder in (build_flight_graph, build_hotel_graph, build_car_graph):
        assert builder() is not None


def test_seed_generators():
    sys.path.insert(0, os.path.dirname(__file__) + "/..")
    from seed_data import gen_flights, gen_hotels, gen_cars

    flights = gen_flights(5)
    assert len(flights) == 5
    assert all("text_description" in f for f in flights)
    assert all("embedded_description" in f for f in flights)

    hotels = gen_hotels(5)
    assert len(hotels) == 5
    assert all("name" in h for h in hotels)

    cars = gen_cars(5)
    assert len(cars) == 5
    assert all("make" in c for c in cars)
