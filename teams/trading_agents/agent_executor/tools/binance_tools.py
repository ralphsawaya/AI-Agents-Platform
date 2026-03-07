"""Binance trading tools for the Executor agent."""

from langchain_core.tools import tool

from shared.binance_client import (
    place_market_order,
    cancel_order as binance_cancel_order,
    get_order_status as binance_get_order_status,
    get_account_balance,
)
from shared.config import TRADING_PAIR, QUOTE_ASSET


@tool
def place_spot_order(side: str, quantity: float, symbol: str = TRADING_PAIR) -> dict:
    """Place a spot market order on Binance."""
    return place_market_order(side=side, quantity=quantity, symbol=symbol)


@tool
def cancel_open_order(order_id: int, symbol: str = TRADING_PAIR) -> dict:
    """Cancel an open order on Binance."""
    return binance_cancel_order(order_id=order_id, symbol=symbol)


@tool
def check_order(order_id: int, symbol: str = TRADING_PAIR) -> dict:
    """Check the status of an order."""
    return binance_get_order_status(order_id=order_id, symbol=symbol)


@tool
def get_balance(asset: str = QUOTE_ASSET) -> float:
    """Get the available balance for an asset."""
    return get_account_balance(asset=asset)
