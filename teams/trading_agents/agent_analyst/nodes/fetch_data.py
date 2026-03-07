"""Fetch OHLCV market data from Binance."""

from shared.binance_client import get_klines
from shared.config import TRADING_PAIR
from shared.logger import get_logger

logger = get_logger("analyst.fetch_data")


def fetch_data(state: dict) -> dict:
    logger.info("Fetching 4h and 1h candles for %s", TRADING_PAIR)
    try:
        ohlcv_4h = get_klines(symbol=TRADING_PAIR, interval="4h", limit=100)
        ohlcv_1h = get_klines(symbol=TRADING_PAIR, interval="1h", limit=100)
        logger.info(
            "Fetched %d 4h candles and %d 1h candles",
            len(ohlcv_4h), len(ohlcv_1h),
        )
        return {
            "ohlcv_4h": ohlcv_4h,
            "ohlcv_1h": ohlcv_1h,
            "status": "data_fetched",
        }
    except Exception as exc:
        logger.error("Failed to fetch market data: %s", exc)
        return {"status": "error", "reasoning": f"Data fetch failed: {exc}"}
