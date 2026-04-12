"""Shared data models for trip agents."""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class FlightResult:
    airline: str = ""
    flight_number: str = ""
    origin: str = ""
    origin_city: str = ""
    destination: str = ""
    destination_city: str = ""
    departure_time: str = ""
    arrival_time: str = ""
    date: str = ""
    price_eur: float = 0.0
    travel_class: str = "economy"
    stops: int = 0
    duration_minutes: int = 0
    score: float = 0.0


@dataclass
class HotelResult:
    name: str = ""
    city: str = ""
    country: str = ""
    stars: int = 0
    price_per_night_eur: float = 0.0
    amenities: list = field(default_factory=list)
    neighborhood: str = ""
    rating: float = 0.0
    room_types: list = field(default_factory=list)
    score: float = 0.0


@dataclass
class CarResult:
    company: str = ""
    make: str = ""
    model: str = ""
    doors: int = 4
    color: str = ""
    category: str = ""
    price_per_day_eur: float = 0.0
    transmission: str = "automatic"
    fuel_type: str = "gasoline"
    pickup_city: str = ""
    score: float = 0.0


@dataclass
class Reservation:
    traveler_name: str = "John Doe"
    flight: dict = field(default_factory=dict)
    hotel: dict = field(default_factory=dict)
    car: dict = field(default_factory=dict)
    trip_dates: dict = field(default_factory=dict)
    total_cost_eur: float = 0.0
    status: str = "confirmed"
    thread_id: str = ""
    agent_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
