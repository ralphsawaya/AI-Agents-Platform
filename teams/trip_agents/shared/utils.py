"""Shared utility functions."""

import json
import os
from datetime import datetime


def load_args() -> dict:
    """Load runtime arguments from the AGENT_ARGS environment variable."""
    raw = os.getenv("AGENT_ARGS", "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def hotel_nights_from_trip_dates(trip_dates: dict | None, default: int = 7) -> int:
    """Compute stay length from trip_dates; fall back to default when missing/invalid."""
    if not trip_dates:
        return default
    start_raw, end_raw = trip_dates.get("start"), trip_dates.get("end")
    if not start_raw or not end_raw:
        return default
    try:
        start = datetime.fromisoformat(str(start_raw))
        end = datetime.fromisoformat(str(end_raw))
        return max((end - start).days, 1)
    except (ValueError, TypeError):
        return default


VALID_RESERVATION_CATEGORIES = frozenset({"flight", "hotel", "car"})
