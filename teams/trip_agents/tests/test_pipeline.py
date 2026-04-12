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
    from orchestrator.state import TripSearchState, TripReserveState
    assert "query" in TripSearchState.__annotations__
    assert "flight_results" in TripSearchState.__annotations__
    assert "hotel_results" in TripSearchState.__annotations__
    assert "car_results" in TripSearchState.__annotations__
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
