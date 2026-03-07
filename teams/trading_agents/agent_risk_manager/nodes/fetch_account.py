"""Fetch current Binance account state."""

from shared.binance_client import (
    get_account_balance, get_current_price, get_open_orders, get_klines,
)
from shared.config import TRADING_PAIR, QUOTE_ASSET, BASE_ASSET
from shared.indicators import klines_to_dataframe, compute_all_indicators
from shared.logger import get_logger

logger = get_logger("risk_manager.fetch_account")


def fetch_account(state: dict) -> dict:
    try:
        usdt_balance = get_account_balance(QUOTE_ASSET)
        btc_balance = get_account_balance(BASE_ASSET)
        current_price = get_current_price(TRADING_PAIR)
        open_orders = get_open_orders(TRADING_PAIR)

        # Current exposure in USDT
        current_exposure = btc_balance * current_price

        # Fetch ATR for stop-loss calculation
        klines = get_klines(symbol=TRADING_PAIR, interval="4h", limit=20)
        df = klines_to_dataframe(klines)
        indicators = compute_all_indicators(df)
        atr = indicators.atr

        logger.info(
            "Account: %.2f USDT, %.8f BTC (%.2f USDT), %d open orders, ATR=%.2f",
            usdt_balance, btc_balance, current_exposure, len(open_orders), atr,
        )

        return {
            "account_balance": usdt_balance,
            "btc_balance": btc_balance,
            "current_price": current_price,
            "current_exposure": current_exposure,
            "open_orders_count": len(open_orders),
            "atr": atr,
            "status": "account_fetched",
        }
    except Exception as exc:
        logger.error("Failed to fetch account data: %s", exc)
        return {
            "status": "error",
            "approved": False,
            "rejection_reason": f"Account fetch failed: {exc}",
        }
