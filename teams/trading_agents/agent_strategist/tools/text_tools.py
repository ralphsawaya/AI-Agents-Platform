"""Strategy selection tools."""

from langchain_core.tools import tool

from shared.mongo import get_strategy_selections


@tool
def get_current_active_strategy() -> str:
    """Get the currently active trading strategy."""
    doc = get_strategy_selections().find_one(sort=[("timestamp", -1)])
    return doc["active_strategy"] if doc else "none"


@tool
def get_strategy_history(limit: int = 10) -> list[dict]:
    """Get recent strategy selection history."""
    cursor = get_strategy_selections().find().sort("timestamp", -1).limit(limit)
    results = []
    for doc in cursor:
        results.append({
            "strategy": doc["active_strategy"],
            "regime": doc.get("regime", ""),
            "confidence": doc.get("confidence", 0),
            "timestamp": str(doc.get("timestamp", "")),
        })
    return results
