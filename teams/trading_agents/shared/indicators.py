"""Technical indicator calculations for market analysis."""

import pandas as pd
import ta

from shared.config import (
    ADX_PERIOD, ATR_PERIOD, BB_PERIOD, BB_STD,
    EMA_FAST, EMA_MID, EMA_SLOW, RSI_PERIOD, VOLUME_MA_PERIOD,
)
from shared.models import Indicators


def klines_to_dataframe(klines: list[list]) -> pd.DataFrame:
    """Convert Binance klines response to a pandas DataFrame."""
    df = pd.DataFrame(klines, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore",
    ])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
    return df


def compute_all_indicators(df: pd.DataFrame) -> Indicators:
    """Compute the full suite of technical indicators from OHLCV data."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    volume = df["volume"]

    # ADX
    adx_indicator = ta.trend.ADXIndicator(high, low, close, window=ADX_PERIOD)
    adx = adx_indicator.adx().iloc[-1]

    # ATR
    atr_indicator = ta.volatility.AverageTrueRange(high, low, close, window=ATR_PERIOD)
    atr = atr_indicator.average_true_range().iloc[-1]
    current_price = close.iloc[-1]
    atr_pct = (atr / current_price) * 100 if current_price > 0 else 0.0

    # Bollinger Bands
    bb = ta.volatility.BollingerBands(close, window=BB_PERIOD, window_dev=BB_STD)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]
    bb_middle = bb.bollinger_mavg().iloc[-1]
    bb_width = bb.bollinger_wband().iloc[-1]

    # EMAs
    ema_fast_series = ta.trend.EMAIndicator(close, window=EMA_FAST).ema_indicator()
    ema_mid_series = ta.trend.EMAIndicator(close, window=EMA_MID).ema_indicator()
    ema_slow_series = ta.trend.EMAIndicator(close, window=EMA_SLOW).ema_indicator()

    ema_fast_val = ema_fast_series.iloc[-1]
    ema_mid_val = ema_mid_series.iloc[-1]
    ema_slow_val = ema_slow_series.iloc[-1]

    # EMA slopes (% change over last 3 periods)
    def _slope(series: pd.Series, lookback: int = 3) -> float:
        if len(series) < lookback + 1:
            return 0.0
        prev = series.iloc[-(lookback + 1)]
        curr = series.iloc[-1]
        return ((curr - prev) / prev) * 100 if prev != 0 else 0.0

    # RSI
    rsi = ta.momentum.RSIIndicator(close, window=RSI_PERIOD).rsi().iloc[-1]

    # MACD
    macd_indicator = ta.trend.MACD(close)
    macd = macd_indicator.macd().iloc[-1]
    macd_signal = macd_indicator.macd_signal().iloc[-1]
    macd_hist = macd_indicator.macd_diff().iloc[-1]

    # Volume ratio (current volume / 20-period MA)
    vol_ma = volume.rolling(window=VOLUME_MA_PERIOD).mean().iloc[-1]
    volume_ratio = volume.iloc[-1] / vol_ma if vol_ma > 0 else 1.0

    return Indicators(
        adx=round(adx, 2),
        atr=round(atr, 2),
        atr_pct=round(atr_pct, 4),
        bb_width=round(bb_width, 4),
        bb_upper=round(bb_upper, 2),
        bb_lower=round(bb_lower, 2),
        bb_middle=round(bb_middle, 2),
        ema_fast=round(ema_fast_val, 2),
        ema_mid=round(ema_mid_val, 2),
        ema_slow=round(ema_slow_val, 2),
        ema_fast_slope=round(_slope(ema_fast_series), 4),
        ema_mid_slope=round(_slope(ema_mid_series), 4),
        ema_slow_slope=round(_slope(ema_slow_series), 4),
        rsi=round(rsi, 2),
        macd=round(macd, 2),
        macd_signal=round(macd_signal, 2),
        macd_hist=round(macd_hist, 2),
        volume_ratio=round(volume_ratio, 2),
        current_price=round(current_price, 2),
    )


def indicators_to_dict(ind: Indicators) -> dict:
    """Convert an Indicators dataclass to a dictionary for storage."""
    return {
        "adx": ind.adx,
        "atr": ind.atr,
        "atr_pct": ind.atr_pct,
        "bb_width": ind.bb_width,
        "bb_upper": ind.bb_upper,
        "bb_lower": ind.bb_lower,
        "bb_middle": ind.bb_middle,
        "ema_fast": ind.ema_fast,
        "ema_mid": ind.ema_mid,
        "ema_slow": ind.ema_slow,
        "ema_fast_slope": ind.ema_fast_slope,
        "ema_mid_slope": ind.ema_mid_slope,
        "ema_slow_slope": ind.ema_slow_slope,
        "rsi": ind.rsi,
        "macd": ind.macd,
        "macd_signal": ind.macd_signal,
        "macd_hist": ind.macd_hist,
        "volume_ratio": ind.volume_ratio,
        "current_price": ind.current_price,
    }
