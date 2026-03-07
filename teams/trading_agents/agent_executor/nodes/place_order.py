"""Place the trade order on Binance."""

from shared.binance_client import place_market_order
from shared.config import TRADING_PAIR
from shared.logger import get_logger

logger = get_logger("executor.place_order")


def place_order(state: dict) -> dict:
    if state.get("status") in ("error", "rejected"):
        return state

    signal = state.get("signal", {})
    risk_params = state.get("risk_params", {})
    dry_run = state.get("dry_run", True)

    action = signal.get("action", "buy")
    position_size = risk_params.get("position_size", 0.0)
    ticker = signal.get("ticker", TRADING_PAIR)

    # Map signal actions to Binance order sides
    if action in ("buy", "close_sell"):
        side = "BUY"
    elif action in ("sell", "close", "close_buy"):
        side = "SELL"
    else:
        return {"status": "error", "order_status": f"unmapped_action:{action}"}

    if dry_run:
        logger.info(
            "[DRY RUN] Would place %s market order: %.8f %s",
            side, position_size, ticker,
        )
        return {
            "order_id": "dry_run_order",
            "fill_price": signal.get("price", 0.0),
            "order_status": "dry_run_filled",
            "status": "order_placed",
        }

    try:
        order = place_market_order(side=side, quantity=position_size, symbol=ticker)
        order_id = str(order.get("orderId", ""))

        # Extract fill price from fills
        fills = order.get("fills", [])
        if fills:
            total_qty = sum(float(f["qty"]) for f in fills)
            total_cost = sum(float(f["price"]) * float(f["qty"]) for f in fills)
            fill_price = total_cost / total_qty if total_qty > 0 else 0
        else:
            fill_price = float(order.get("price", 0))

        logger.info(
            "Order placed: id=%s, side=%s, qty=%.8f, fill=%.2f, status=%s",
            order_id, side, position_size, fill_price, order.get("status"),
        )

        return {
            "order_id": order_id,
            "fill_price": fill_price,
            "order_status": order.get("status", "FILLED"),
            "status": "order_placed",
        }

    except Exception as exc:
        logger.error("Order placement failed: %s", exc)
        return {
            "order_id": "",
            "fill_price": 0.0,
            "order_status": f"failed:{exc}",
            "status": "error",
        }
