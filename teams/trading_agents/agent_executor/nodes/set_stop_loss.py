"""Place a protective stop-loss order after the main order fills."""

from shared.binance_client import place_oco_order
from shared.config import TRADING_PAIR
from shared.logger import get_logger

logger = get_logger("executor.set_stop_loss")


def set_stop_loss(state: dict) -> dict:
    if state.get("status") in ("error", "rejected"):
        return state

    dry_run = state.get("dry_run", True)
    risk_params = state.get("risk_params", {})
    signal = state.get("signal", {})

    stop_loss_price = risk_params.get("stop_loss_price", 0.0)
    take_profit_price = risk_params.get("take_profit_price", 0.0)
    position_size = risk_params.get("position_size", 0.0)
    action = signal.get("action", "")
    ticker = signal.get("ticker", TRADING_PAIR)

    if stop_loss_price <= 0 or position_size <= 0:
        logger.info("No stop-loss to set (SL=%.2f, size=%.8f)", stop_loss_price, position_size)
        return {"status": "complete"}

    # For a BUY entry, we need a SELL OCO for exit
    # For a SELL entry, we need a BUY OCO for exit
    if action in ("buy", "close_sell"):
        oco_side = "SELL"
    elif action in ("sell", "close", "close_buy"):
        oco_side = "BUY"
    else:
        logger.info("Skipping OCO for action: %s", action)
        return {"status": "complete"}

    if dry_run:
        logger.info(
            "[DRY RUN] Would place OCO %s: qty=%.8f, TP=%.2f, SL=%.2f",
            oco_side, position_size, take_profit_price, stop_loss_price,
        )
        return {"stop_loss_order_id": "dry_run_oco", "status": "complete"}

    try:
        # Stop-limit price slightly worse than stop price to ensure fill
        if oco_side == "SELL":
            stop_limit_price = stop_loss_price * 0.999
        else:
            stop_limit_price = stop_loss_price * 1.001

        order = place_oco_order(
            side=oco_side,
            quantity=position_size,
            price=take_profit_price,
            stop_price=stop_loss_price,
            stop_limit_price=round(stop_limit_price, 2),
            symbol=ticker,
        )

        oco_id = str(order.get("orderListId", ""))
        logger.info("OCO order placed: %s", oco_id)
        return {"stop_loss_order_id": oco_id, "status": "complete"}

    except Exception as exc:
        logger.error("Failed to place OCO: %s", exc)
        return {"stop_loss_order_id": "", "status": "complete"}
