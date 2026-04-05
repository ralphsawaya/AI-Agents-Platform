"""Write the active strategy selection to MongoDB.

When the strategy changes, all open Binance orders are cancelled so that
OCO stop-loss/take-profit orders from the previous strategy don't interfere
with the new one.
"""

from datetime import datetime, timezone

from shared.logger import get_logger
from shared.mongo import get_strategy_selections

logger = get_logger("strategist.update_selection")


def _cancel_open_orders_on_switch(previous: str, selected: str) -> None:
    """Cancel all open Binance orders when the active strategy changes."""
    try:
        from shared.binance_client import get_open_orders, cancel_order
        from shared.config import TRADING_PAIR

        open_orders = get_open_orders(TRADING_PAIR)
        if not open_orders:
            logger.info("No open orders to cancel on strategy switch")
            return

        cancelled = 0
        for order in open_orders:
            try:
                cancel_order(order["orderId"], TRADING_PAIR)
                cancelled += 1
            except Exception as exc:
                logger.warning("Failed to cancel order %s: %s", order["orderId"], exc)

        logger.info(
            "Strategy switch %s → %s: cancelled %d/%d open orders",
            previous, selected, cancelled, len(open_orders),
        )
    except Exception as exc:
        logger.error("Failed to cancel open orders on strategy switch: %s", exc)


def update_selection(state: dict) -> dict:
    selected = state.get("selected_strategy", "")
    if not selected:
        return {"status": "error", "reasoning": "No strategy selected"}

    # Check if the strategy is actually changing
    prev_doc = get_strategy_selections().find_one(sort=[("timestamp", -1)])
    previous = prev_doc["active_strategy"] if prev_doc else None

    if previous and previous != selected:
        logger.info("Strategy changing: %s → %s", previous, selected)
        _cancel_open_orders_on_switch(previous, selected)

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
