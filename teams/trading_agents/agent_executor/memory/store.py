"""Memory store for the Executor — trade history."""

from shared.mongo import get_trades


def get_recent_trades(limit: int = 20) -> list[dict]:
    """Retrieve the most recent trades."""
    col = get_trades()
    cursor = col.find().sort("timestamp", -1).limit(limit)
    return list(cursor)
