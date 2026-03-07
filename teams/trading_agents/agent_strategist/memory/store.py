"""Memory store for the Strategist agent — strategy history."""

from shared.mongo import get_strategy_selections


def get_recent_selections(limit: int = 10) -> list[dict]:
    """Retrieve the most recent strategy selections."""
    col = get_strategy_selections()
    cursor = col.find().sort("timestamp", -1).limit(limit)
    return list(cursor)
