"""Calculate position size, stop-loss, and take-profit levels.

ATR is fetched on 4H for all WF-validated strategies (ema_trend,
rsi_momentum, macd_trend) — see fetch_account.py.

  - ema_trend: 3x ATR — rides trends with wide trail, cross+trail exit.
  - rsi_momentum: 3x ATR — trail-only exit, needs wider disaster stop.
  - macd_trend: 3x ATR — trail-only exit, needs wider disaster stop.
"""

from shared.config import MAX_RISK_PER_TRADE, MAX_OPEN_POSITIONS, MAX_DRAWDOWN
from shared.logger import get_logger

logger = get_logger("risk_manager.calculate_risk")

STRATEGY_ATR_MULT = {
    "ema_trend": 3.0,
    "rsi_momentum": 3.0,
    "macd_trend": 3.0,
}

STRATEGY_TP_RATIO = {
    "ema_trend": 3.0,
    "rsi_momentum": 3.0,
    "macd_trend": 3.0,
}

DEFAULT_ATR_MULT = 2.5
DEFAULT_TP_RATIO = 2.5


def calculate_risk(state: dict) -> dict:
    if state.get("status") == "error":
        return state

    signal = state.get("signal", {})
    action = signal.get("action", "")
    strategy_name = signal.get("strategy_name", "")

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

    risk_amount = total_portfolio * MAX_RISK_PER_TRADE

    atr_mult = STRATEGY_ATR_MULT.get(strategy_name, DEFAULT_ATR_MULT)
    tp_ratio = STRATEGY_TP_RATIO.get(strategy_name, DEFAULT_TP_RATIO)
    stop_distance = atr * atr_mult if atr > 0 else current_price * 0.02

    if strategy_name in ("ema_trend", "macd_trend"):
        logger.info(
            "%s: using %.1fx ATR disaster stop (trailing stop handles normal exits)",
            strategy_name, atr_mult,
        )

    if stop_distance > 0:
        position_size_btc = risk_amount / stop_distance
    else:
        position_size_btc = risk_amount / (current_price * 0.02)

    max_affordable = account_balance / current_price if current_price > 0 else 0
    position_size_btc = min(position_size_btc, max_affordable * 0.95)

    if action in ("buy", "close_sell"):
        stop_loss_price = current_price - stop_distance
        take_profit_price = current_price + (stop_distance * tp_ratio)
    elif action in ("sell", "close_buy", "close"):
        stop_loss_price = current_price + stop_distance
        take_profit_price = current_price - (stop_distance * tp_ratio)
    else:
        stop_loss_price = 0.0
        take_profit_price = 0.0

    position_size_btc = round(position_size_btc, 5)

    logger.info(
        "Risk calc [%s]: size=%.5f BTC (%.2f USDT), SL=%.2f (%.1fx ATR), TP=%.2f, risk=%.2f USDT",
        strategy_name or "unknown",
        position_size_btc,
        position_size_btc * current_price,
        stop_loss_price,
        atr_mult,
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
