"""Write the active strategy selection to MongoDB."""

from datetime import datetime, timezone

from shared.logger import get_logger
from shared.mongo import get_strategy_selections

logger = get_logger("strategist.update_selection")


def update_selection(state: dict) -> dict:
    selected = state.get("selected_strategy", "")
    if not selected:
        return {"status": "error", "reasoning": "No strategy selected"}

    doc = {
        "active_strategy": selected,
        "regime": state.get("regime", ""),
        "confidence": state.get("confidence", 0.0),
        "reasoning": state.get("reasoning", ""),
        "timestamp": datetime.now(timezone.utc),
    }

    get_strategy_selections().insert_one(doc)
    logger.info("Active strategy updated to '%s' in MongoDB", selected)

    return {"status": "selection_stored"}
