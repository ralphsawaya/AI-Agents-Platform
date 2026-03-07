"""Binance Spot API wrapper for trading agents."""

from binance.client import Client
from binance.exceptions import BinanceAPIException

from shared.config import BINANCE_API_KEY, BINANCE_API_SECRET, TRADING_PAIR
from shared.logger import get_logger

logger = get_logger("shared.binance_client")

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
    return _client


def get_klines(symbol: str = TRADING_PAIR, interval: str = "4h", limit: int = 100) -> list[list]:
    """Fetch OHLCV candlestick data from Binance."""
    client = get_client()
    return client.get_klines(symbol=symbol, interval=interval, limit=limit)


def get_current_price(symbol: str = TRADING_PAIR) -> float:
    """Get the latest price for a symbol."""
    client = get_client()
    ticker = client.get_symbol_ticker(symbol=symbol)
    return float(ticker["price"])


def get_account_balance(asset: str = "USDT") -> float:
    """Get the free balance for a given asset."""
    client = get_client()
    account = client.get_account()
    for balance in account["balances"]:
        if balance["asset"] == asset:
            return float(balance["free"])
    return 0.0


def get_all_balances() -> dict[str, float]:
    """Get all non-zero balances."""
    client = get_client()
    account = client.get_account()
    return {
        b["asset"]: float(b["free"])
        for b in account["balances"]
        if float(b["free"]) > 0 or float(b["locked"]) > 0
    }


def get_open_orders(symbol: str = TRADING_PAIR) -> list[dict]:
    """Get all open orders for a symbol."""
    client = get_client()
    return client.get_open_orders(symbol=symbol)


def place_market_order(side: str, quantity: float, symbol: str = TRADING_PAIR) -> dict:
    """Place a market buy or sell order."""
    client = get_client()
    logger.info("Placing %s market order: %.8f %s", side, quantity, symbol)
    try:
        order = client.create_order(
            symbol=symbol,
            side=side.upper(),
            type="MARKET",
            quantity=f"{quantity:.8f}",
        )
        logger.info("Order placed: %s", order["orderId"])
        return order
    except BinanceAPIException as e:
        logger.error("Binance API error: %s", e)
        raise


def place_limit_order(
    side: str, quantity: float, price: float, symbol: str = TRADING_PAIR,
) -> dict:
    """Place a limit buy or sell order."""
    client = get_client()
    logger.info("Placing %s limit order: %.8f @ %.2f %s", side, quantity, price, symbol)
    try:
        order = client.create_order(
            symbol=symbol,
            side=side.upper(),
            type="LIMIT",
            timeInForce="GTC",
            quantity=f"{quantity:.8f}",
            price=f"{price:.2f}",
        )
        return order
    except BinanceAPIException as e:
        logger.error("Binance API error: %s", e)
        raise


def place_oco_order(
    side: str,
    quantity: float,
    price: float,
    stop_price: float,
    stop_limit_price: float,
    symbol: str = TRADING_PAIR,
) -> dict:
    """Place an OCO (One-Cancels-the-Other) order for stop-loss + take-profit."""
    client = get_client()
    logger.info(
        "Placing OCO %s: qty=%.8f, price=%.2f, stop=%.2f",
        side, quantity, price, stop_price,
    )
    try:
        order = client.create_oco_order(
            symbol=symbol,
            side=side.upper(),
            quantity=f"{quantity:.8f}",
            price=f"{price:.2f}",
            stopPrice=f"{stop_price:.2f}",
            stopLimitPrice=f"{stop_limit_price:.2f}",
            stopLimitTimeInForce="GTC",
        )
        return order
    except BinanceAPIException as e:
        logger.error("Binance OCO error: %s", e)
        raise


def get_order_status(order_id: int, symbol: str = TRADING_PAIR) -> dict:
    """Get the status of an order."""
    client = get_client()
    return client.get_order(symbol=symbol, orderId=order_id)


def cancel_order(order_id: int, symbol: str = TRADING_PAIR) -> dict:
    """Cancel an open order."""
    client = get_client()
    return client.cancel_order(symbol=symbol, orderId=order_id)


def get_symbol_info(symbol: str = TRADING_PAIR) -> dict:
    """Get symbol trading rules (min qty, step size, etc.)."""
    client = get_client()
    info = client.get_symbol_info(symbol)
    return info
