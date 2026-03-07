"""Compute technical indicators from OHLCV data."""

from shared.indicators import klines_to_dataframe, compute_all_indicators, indicators_to_dict
from shared.logger import get_logger

logger = get_logger("analyst.compute_indicators")


def compute_indicators(state: dict) -> dict:
    if state.get("status") == "error":
        return state

    ohlcv_4h = state.get("ohlcv_4h", [])
    if not ohlcv_4h:
        logger.error("No 4h OHLCV data available")
        return {"status": "error", "reasoning": "No OHLCV data"}

    df = klines_to_dataframe(ohlcv_4h)
    indicators = compute_all_indicators(df)
    ind_dict = indicators_to_dict(indicators)

    logger.info(
        "Indicators computed — Price: %.2f | ADX: %.2f | ATR: %.2f | RSI: %.2f | BB Width: %.4f",
        indicators.current_price,
        indicators.adx,
        indicators.atr,
        indicators.rsi,
        indicators.bb_width,
    )

    return {"indicators": ind_dict, "status": "indicators_computed"}
