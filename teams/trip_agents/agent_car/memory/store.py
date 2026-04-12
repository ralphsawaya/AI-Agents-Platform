"""Memory store for the Car Rental Search agent."""

from shared.atlas import get_cars


def get_recent_searches(limit: int = 10) -> list[dict]:
    return list(get_cars().find({}, {"embedded_description": 0}).limit(limit))
