"""Final risk gate: approve or reject the trade."""

from datetime import datetime, timezone

from shared.config import MAX_OPEN_POSITIONS, MAX_DRAWDOWN
from shared.logger import get_logger
from shared.mongo import get_trades, get_risk_state

logger = get_logger("risk_manager.approve_trade")

MIN_POSITION_USDT = 10.0


def approve_trade(state: dict) -> dict:
    if state.get("status") == "error":
        return state

    position_size = state.get("position_size", 0.0)
    current_price = state.get("current_price", 0.0)
    account_balance = state.get("account_balance", 0.0)
    current_exposure = state.get("current_exposure", 0.0)
    open_orders_count = state.get("open_orders_count", 0)
    signal = state.get("signal", {})
    action = signal.get("action", "")

    total_portfolio = account_balance + current_exposure
    position_value = position_size * current_price

    # --- Risk checks ---

    # Check: minimum position size
    if position_value < MIN_POSITION_USDT:
        reason = f"Position too small: {position_value:.2f} USDT (min {MIN_POSITION_USDT})"
        logger.warning(reason)
        return {"approved": False, "rejection_reason": reason, "status": "trade_rejected"}

    # Check: max open positions
    if open_orders_count >= MAX_OPEN_POSITIONS:
        reason = f"Max open positions reached: {open_orders_count}/{MAX_OPEN_POSITIONS}"
        logger.warning(reason)
        return {"approved": False, "rejection_reason": reason, "status": "trade_rejected"}

    # Check: drawdown limit
    drawdown = _calculate_drawdown()
    if drawdown > MAX_DRAWDOWN:
        reason = f"Max drawdown exceeded: {drawdown:.1%} > {MAX_DRAWDOWN:.1%}"
        logger.warning(reason)
        return {"approved": False, "rejection_reason": reason, "status": "trade_rejected"}

    # Check: sufficient balance for buys
    if action == "buy" and position_value > account_balance * 0.95:
        reason = f"Insufficient balance: need {position_value:.2f}, have {account_balance:.2f}"
        logger.warning(reason)
        return {"approved": False, "rejection_reason": reason, "status": "trade_rejected"}

    # Check: have BTC to sell
    if action in ("sell", "close") and state.get("btc_balance", 0) < position_size:
        adjusted = state.get("btc_balance", 0.0)
        if adjusted * current_price < MIN_POSITION_USDT:
            reason = f"Insufficient BTC to sell: {adjusted:.8f}"
            logger.warning(reason)
            return {"approved": False, "rejection_reason": reason, "status": "trade_rejected"}
        logger.info("Adjusted sell size to available BTC: %.8f", adjusted)
        return {
            "position_size": adjusted,
            "approved": True,
            "rejection_reason": "",
            "status": "trade_approved",
        }

    logger.info("Trade APPROVED: %s %.5f BTC (%.2f USDT)", action, position_size, position_value)

    # Update risk state
    _update_risk_state(total_portfolio, drawdown)

    return {"approved": True, "rejection_reason": "", "status": "trade_approved"}


def _calculate_drawdown() -> float:
    """Calculate current drawdown from peak portfolio value."""
    risk_col = get_risk_state()
    state_doc = risk_col.find_one(sort=[("updated_at", -1)])
    if not state_doc:
        return 0.0

    peak = state_doc.get("peak_portfolio", 0)
    current = state_doc.get("current_portfolio", 0)
    if peak <= 0:
        return 0.0
    return max(0.0, (peak - current) / peak)


def _update_risk_state(current_portfolio: float, drawdown: float) -> None:
    """Update the risk state document with latest portfolio value."""
    risk_col = get_risk_state()
    state_doc = risk_col.find_one(sort=[("updated_at", -1)])
    peak = max(current_portfolio, state_doc.get("peak_portfolio", 0) if state_doc else 0)

    risk_col.update_one(
        {},
        {
            "$set": {
                "current_portfolio": current_portfolio,
                "peak_portfolio": peak,
                "current_drawdown": drawdown,
                "updated_at": datetime.now(timezone.utc),
            },
        },
        upsert=True,
    )
