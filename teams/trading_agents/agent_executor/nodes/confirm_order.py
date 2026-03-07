"""Confirm order fill and record the trade in MongoDB."""

import time
from datetime import datetime, timezone

from shared.binance_client import get_order_status
from shared.config import TRADING_PAIR
from shared.logger import get_logger
from shared.mongo import get_trades

logger = get_logger("executor.confirm_order")

MAX_POLL_ATTEMPTS = 5
POLL_INTERVAL = 2


def confirm_order(state: dict) -> dict:
    if state.get("status") in ("error", "rejected"):
        return state

    order_id = state.get("order_id", "")
    dry_run = state.get("dry_run", True)
    signal = state.get("signal", {})
    risk_params = state.get("risk_params", {})

    if dry_run or order_id == "dry_run_order":
        trade_record = _build_trade_record(state, is_dry_run=True)
        get_trades().insert_one(trade_record)
        logger.info("[DRY RUN] Trade recorded in MongoDB")
        return {"trade_record": trade_record, "status": "trade_recorded"}

    # Poll for order fill
    fill_price = state.get("fill_price", 0.0)
    final_status = state.get("order_status", "")
    ticker = signal.get("ticker", TRADING_PAIR)

    for attempt in range(MAX_POLL_ATTEMPTS):
        try:
            order_info = get_order_status(int(order_id), symbol=ticker)
            final_status = order_info.get("status", "")

            if final_status in ("FILLED", "PARTIALLY_FILLED"):
                fill_price = float(order_info.get("price", 0)) or fill_price
                logger.info(
                    "Order %s confirmed: %s @ %.2f",
                    order_id, final_status, fill_price,
                )
                break
            elif final_status in ("CANCELED", "REJECTED", "EXPIRED"):
                logger.warning("Order %s: %s", order_id, final_status)
                break

            logger.info("Order %s: %s (attempt %d/%d)", order_id, final_status, attempt + 1, MAX_POLL_ATTEMPTS)
            time.sleep(POLL_INTERVAL)

        except Exception as exc:
            logger.error("Failed to check order status: %s", exc)
            break

    trade_record = _build_trade_record(state, is_dry_run=False)
    trade_record["order_status"] = final_status
    trade_record["fill_price"] = fill_price

    get_trades().insert_one(trade_record)
    logger.info("Trade recorded: %s", trade_record.get("_id", ""))

    return {
        "fill_price": fill_price,
        "order_status": final_status,
        "trade_record": trade_record,
        "status": "trade_recorded",
    }


def _build_trade_record(state: dict, is_dry_run: bool) -> dict:
    signal = state.get("signal", {})
    risk_params = state.get("risk_params", {})

    return {
        "order_id": state.get("order_id", ""),
        "side": signal.get("action", ""),
        "strategy_name": signal.get("strategy_name", ""),
        "ticker": signal.get("ticker", TRADING_PAIR),
        "quantity": risk_params.get("position_size", 0.0),
        "signal_price": signal.get("price", 0.0),
        "fill_price": state.get("fill_price", 0.0),
        "stop_loss_price": risk_params.get("stop_loss_price", 0.0),
        "take_profit_price": risk_params.get("take_profit_price", 0.0),
        "risk_amount": risk_params.get("risk_amount", 0.0),
        "status": state.get("order_status", ""),
        "dry_run": is_dry_run,
        "timestamp": datetime.now(timezone.utc),
    }
