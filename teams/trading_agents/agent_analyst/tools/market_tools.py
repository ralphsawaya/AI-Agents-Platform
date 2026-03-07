"""Market data tools for the Analyst agent."""

from langchain_core.tools import tool

from shared.binance_client import get_current_price, get_klines
from shared.config import TRADING_PAIR
from shared.indicators import klines_to_dataframe, compute_all_indicators, indicators_to_dict


@tool
def fetch_current_price(symbol: str = TRADING_PAIR) -> float:
    """Fetch the current price for a trading pair."""
    return get_current_price(symbol)


@tool
def fetch_indicators(symbol: str = TRADING_PAIR, interval: str = "4h") -> dict:
    """Fetch OHLCV data and compute all technical indicators."""
    klines = get_klines(symbol=symbol, interval=interval, limit=100)
    df = klines_to_dataframe(klines)
    indicators = compute_all_indicators(df)
    return indicators_to_dict(indicators)
