"""Calculate position size, stop-loss, and take-profit levels."""

from shared.config import MAX_RISK_PER_TRADE, MAX_OPEN_POSITIONS, MAX_DRAWDOWN
from shared.logger import get_logger

logger = get_logger("risk_manager.calculate_risk")


def calculate_risk(state: dict) -> dict:
    if state.get("status") == "error":
        return state

    signal = state.get("signal", {})
    action = signal.get("action", "")
    signal_price = signal.get("price", 0.0)

    account_balance = state.get("account_balance", 0.0)
    current_price = state.get("current_price", 0.0)
    current_exposure = state.get("current_exposure", 0.0)
    atr = state.get("atr", 0.0)

    total_portfolio = account_balance + current_exposure

    if total_portfolio <= 0:
        return {
            "approved": False,
            "rejection_reason": "No portfolio value detected",
            "status": "risk_calculated",
        }

    # Max risk amount per trade
    risk_amount = total_portfolio * MAX_RISK_PER_TRADE

    # Stop-loss distance based on ATR (1.5x ATR)
    stop_distance = atr * 1.5 if atr > 0 else current_price * 0.02

    # Position size: risk_amount / stop_distance (in BTC)
    if stop_distance > 0:
        position_size_btc = risk_amount / stop_distance
    else:
        position_size_btc = risk_amount / (current_price * 0.02)

    # Cap position size at available balance
    max_affordable = account_balance / current_price if current_price > 0 else 0
    position_size_btc = min(position_size_btc, max_affordable * 0.95)

    # Calculate stop-loss and take-profit prices
    if action in ("buy", "close_sell"):
        stop_loss_price = current_price - stop_distance
        take_profit_price = current_price + (stop_distance * 2)
    elif action in ("sell", "close_buy", "close"):
        stop_loss_price = current_price + stop_distance
        take_profit_price = current_price - (stop_distance * 2)
    else:
        stop_loss_price = 0.0
        take_profit_price = 0.0

    # Round BTC to 5 decimal places (Binance minimum step)
    position_size_btc = round(position_size_btc, 5)

    logger.info(
        "Risk calc: size=%.5f BTC (%.2f USDT), SL=%.2f, TP=%.2f, risk=%.2f USDT",
        position_size_btc,
        position_size_btc * current_price,
        stop_loss_price,
        take_profit_price,
        risk_amount,
    )

    return {
        "position_size": position_size_btc,
        "stop_loss_price": round(stop_loss_price, 2),
        "take_profit_price": round(take_profit_price, 2),
        "risk_amount": round(risk_amount, 2),
        "status": "risk_calculated",
    }
