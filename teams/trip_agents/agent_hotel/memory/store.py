"""Memory store for the Hotel Search agent."""

from shared.atlas import get_hotels


def get_recent_searches(limit: int = 10) -> list[dict]:
    return list(get_hotels().find({}, {"embedded_description": 0}).limit(limit))
