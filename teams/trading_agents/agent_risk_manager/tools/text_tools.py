"""Risk management tools."""

from langchain_core.tools import tool

from shared.binance_client import get_account_balance, get_open_orders
from shared.config import TRADING_PAIR, QUOTE_ASSET


@tool
def check_available_balance() -> float:
    """Check available USDT balance."""
    return get_account_balance(QUOTE_ASSET)


@tool
def count_open_orders(symbol: str = TRADING_PAIR) -> int:
    """Count open orders for a symbol."""
    return len(get_open_orders(symbol))
