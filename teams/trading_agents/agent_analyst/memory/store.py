"""Memory store for the Analyst agent — regime history."""

from shared.mongo import get_market_regimes


def get_recent_regimes(limit: int = 10) -> list[dict]:
    """Retrieve the most recent regime classifications."""
    col = get_market_regimes()
    cursor = col.find().sort("timestamp", -1).limit(limit)
    return list(cursor)
