"""Validate the incoming trade signal before execution."""

from shared.logger import get_logger
from shared.mongo import get_strategy_selections

logger = get_logger("executor.validate_signal")

VALID_ACTIONS = {"buy", "sell", "close", "close_buy", "close_sell"}


def validate_signal(state: dict) -> dict:
    signal = state.get("signal", {})
    risk_params = state.get("risk_params", {})

    action = signal.get("action", "")
    strategy_name = signal.get("strategy_name", "")
    ticker = signal.get("ticker", "")

    if not action or action not in VALID_ACTIONS:
        logger.error("Invalid action: '%s'", action)
        return {"status": "error", "order_status": f"invalid_action:{action}"}

    if not ticker:
        logger.error("No ticker in signal")
        return {"status": "error", "order_status": "missing_ticker"}

    if not risk_params.get("approved"):
        reason = risk_params.get("rejection_reason", "not approved")
        logger.warning("Trade not approved by Risk Manager: %s", reason)
        return {"status": "rejected", "order_status": f"risk_rejected:{reason}"}

    # Verify strategy still matches active
    doc = get_strategy_selections().find_one(sort=[("timestamp", -1)])
    active_strategy = doc["active_strategy"] if doc else None

    if active_strategy and active_strategy != strategy_name:
        logger.warning(
            "Strategy mismatch: signal=%s, active=%s — proceeding with caution",
            strategy_name, active_strategy,
        )

    logger.info("Signal validated: %s %s @ %.2f", action, ticker, signal.get("price", 0))
    return {"status": "signal_validated"}
