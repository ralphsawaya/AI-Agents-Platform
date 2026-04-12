"""Memory store for the Flight Search agent."""

from shared.atlas import get_flights


def get_recent_searches(limit: int = 10) -> list[dict]:
    col = get_flights()
    return list(col.find({}, {"embedded_description": 0}).limit(limit))
