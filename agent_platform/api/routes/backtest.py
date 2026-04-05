"""Walk-Forward Analysis backtesting API — Binance USDT-M Futures edition.

Implements three walk-forward validated strategies for BTC/USDT 4H:
- EMA Trend: cross+trail exit, ema_slow>=40
- RSI Momentum: trail-only exit (no opposite RSI cross)
- MACD Trend: trail-only exit (no opposite histogram cross)

Legacy strategies (breakout, accumulation, etc.) are still supported for
backward compatibility with existing backtest runs.
"""

import json
import logging
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/backtest", tags=["backtest"])

_STRATEGY_TIMEFRAMES = {
    "ema_trend": "4h",
    "rsi_momentum": "4h",
    "macd_trend": "4h",
    # Legacy
    "pullback": "1h",
    "trend_following": "4h",
    "mean_reversion": "2h",
    "swing_momentum": "4h",
    "breakout": "4h",
    "accumulation": "2h",
}

_PERIODS_PER_YEAR = {
    "15m": 4 * 24 * 365,
    "1h": 24 * 365,
    "2h": 12 * 365,
    "4h": 6 * 365,
    "1d": 365,
}


# ── JSON encoder for numpy types ──────────────────────────────────────

class _NpEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, pd.Timestamp):
            return o.strftime("%Y-%m-%d")
        return super().default(o)


def _dumps(obj: dict) -> str:
    return json.dumps(obj, cls=_NpEncoder)


# ── Technical Indicators ──────────────────────────────────────────────
# All smoothing uses Wilder's RMA (alpha=1/period) to match TradingView's
# ta.rsi, ta.atr, ta.adx implementations.


def _rma(series: pd.Series, period: int) -> pd.Series:
    """Wilder's Running Moving Average (RMA), matching TradingView's ta.rma."""
    return series.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def _ema(close: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(close).ewm(span=period, adjust=False).mean().values


def _sma(v: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(v).rolling(period, min_periods=period).mean().values


def _rsi(close: np.ndarray, period: int) -> np.ndarray:
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_g = _rma(pd.Series(gain), period).values
    avg_l = _rma(pd.Series(loss), period).values
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_g / avg_l
    return 100.0 - 100.0 / (1.0 + rs)


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    prev_c = np.roll(close, 1)
    prev_c[0] = close[0]
    tr = np.maximum(
        high - low,
        np.maximum(np.abs(high - prev_c), np.abs(low - prev_c)),
    )
    return _rma(pd.Series(tr), period).values


def _bb(close: np.ndarray, period: int, num_std: float):
    s = pd.Series(close)
    mid = s.rolling(period, min_periods=period).mean()
    std = s.rolling(period, min_periods=period).std()
    return mid.values, (mid + num_std * std).values, (mid - num_std * std).values


def _adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int):
    prev_h = np.roll(high, 1); prev_h[0] = high[0]
    prev_l = np.roll(low, 1); prev_l[0] = low[0]
    prev_c = np.roll(close, 1); prev_c[0] = close[0]

    up = high - prev_h
    dn = prev_l - low
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)

    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_c), np.abs(low - prev_c)))
    atr_s = _rma(pd.Series(tr), period).values

    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100.0 * _rma(pd.Series(plus_dm), period).values / atr_s
        minus_di = 100.0 * _rma(pd.Series(minus_dm), period).values / atr_s
        dx = 100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di)

    adx_vals = _rma(pd.Series(dx), period).values
    return adx_vals


def _macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    s = pd.Series(close)
    macd_line = s.ewm(span=fast, adjust=False).mean() - s.ewm(span=slow, adjust=False).mean()
    sig_line = macd_line.ewm(span=signal, adjust=False).mean()
    return (macd_line - sig_line).values


def _vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, period: int = 20):
    hlc3 = (high + low + close) / 3.0
    cum_vp = pd.Series(hlc3 * volume).rolling(period, min_periods=1).sum()
    cum_v = pd.Series(volume).rolling(period, min_periods=1).sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        return (cum_vp / cum_v).values


def _donchian(high: np.ndarray, low: np.ndarray, period: int):
    upper = pd.Series(high).rolling(period, min_periods=period).max().values
    lower = pd.Series(low).rolling(period, min_periods=period).min().values
    mid = (upper + lower) / 2.0
    return upper, lower, mid


# ── Strategy Execution ────────────────────────────────────────────────

def _execute(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    volume: np.ndarray,
    strategy: str,
    params: dict,
    fee_pct: float,
    slip_pct: float,
) -> tuple:
    """Run strategy with long+short support. pos: +1 long, -1 short, 0 flat."""
    n = len(close)
    pos = np.zeros(n, dtype=np.float64)

    if strategy == "pullback":
        ema_slow = _ema(close, params["ema_slow"])
        ema_fast = _ema(close, params["ema_fast"])
        rsi_v = _rsi(close, 14)
        atr_v = _atr(high, low, close, 14)
        vol_ma = _sma(volume, 20)
        adx_v = _adx(high, low, close, 14)

        trend_lb = params.get("trend_lb", 12)
        cooldown = params.get("cooldown", 12)
        max_hold = params.get("max_hold", 48)
        min_slope = params.get("min_slope", 0.15)
        adx_min = params.get("adx_min", 20)
        direction = 0
        trail = 0.0
        bars_since_exit = cooldown
        bars_held = 0
        for i in range(trend_lb + 1, n):
            if np.isnan(ema_slow[i]) or np.isnan(ema_fast[i]) or np.isnan(rsi_v[i]) or np.isnan(atr_v[i]) or np.isnan(vol_ma[i]) or np.isnan(adx_v[i]):
                continue

            slope_pct = (ema_slow[i] - ema_slow[i - trend_lb]) / ema_slow[i - trend_lb] * 100
            trend_up = slope_pct > min_slope and adx_v[i] > adx_min
            trend_dn = slope_pct < -min_slope and adx_v[i] > adx_min
            vol_ok = vol_ma[i] > 0 and volume[i] > vol_ma[i] * params["vol_thresh"]
            rsi_was_low = any(rsi_v[max(0, i - k)] < 40 for k in range(1, 5) if not np.isnan(rsi_v[max(0, i - k)]))
            rsi_was_high = any(rsi_v[max(0, i - k)] > 60 for k in range(1, 5) if not np.isnan(rsi_v[max(0, i - k)]))
            pulled_back_up = close[i] > ema_fast[i] and close[i - 1] <= ema_fast[i - 1]
            pulled_back_dn = close[i] < ema_fast[i] and close[i - 1] >= ema_fast[i - 1]

            if direction == 0:
                bars_since_exit += 1
                if bars_since_exit < cooldown:
                    continue
                if trend_up and pulled_back_up and rsi_was_low and rsi_v[i] > 40 and vol_ok:
                    direction = 1
                    trail = close[i] - atr_v[i] * params["atr_trail"]
                    pos[i] = 1
                    bars_held = 0
                elif trend_dn and pulled_back_dn and rsi_was_high and rsi_v[i] < 60 and vol_ok:
                    direction = -1
                    trail = close[i] + atr_v[i] * params["atr_trail"]
                    pos[i] = -1
                    bars_held = 0
            elif direction == 1:
                bars_held += 1
                trail = max(trail, close[i] - atr_v[i] * params["atr_trail"])
                if close[i] <= trail or bars_held >= max_hold:
                    direction = 0
                    bars_since_exit = 0
                else:
                    pos[i] = 1
            else:  # direction == -1
                bars_held += 1
                trail = min(trail, close[i] + atr_v[i] * params["atr_trail"])
                if close[i] >= trail or bars_held >= max_hold:
                    direction = 0
                    bars_since_exit = 0
                else:
                    pos[i] = -1

    elif strategy == "trend_following":
        ema_f = _ema(close, params["ema_fast"])
        ema_m = _ema(close, params["ema_mid"])
        ema_s = _ema(close, params.get("ema_slow", 50))
        adx_v = _adx(high, low, close, 14)
        macd_h = _macd(close)
        atr_v = _atr(high, low, close, 14)

        direction = 0
        trail = 0.0
        for i in range(1, n):
            if np.isnan(ema_f[i]) or np.isnan(ema_m[i]) or np.isnan(ema_s[i]) or np.isnan(adx_v[i]) or np.isnan(macd_h[i]) or np.isnan(atr_v[i]):
                continue
            bull_cross = ema_f[i] > ema_m[i] and ema_f[i - 1] <= ema_m[i - 1]
            bear_cross = ema_f[i] < ema_m[i] and ema_f[i - 1] >= ema_m[i - 1]
            bull_align = ema_f[i] > ema_m[i] > ema_s[i]
            bear_align = ema_f[i] < ema_m[i] < ema_s[i]

            if direction == 0:
                if bull_cross and bull_align and adx_v[i] > params["adx_thresh"] and macd_h[i] > 0:
                    direction = 1
                    trail = close[i] - atr_v[i] * params["atr_trail"]
                    pos[i] = 1
                elif bear_cross and bear_align and adx_v[i] > params["adx_thresh"] and macd_h[i] < 0:
                    direction = -1
                    trail = close[i] + atr_v[i] * params["atr_trail"]
                    pos[i] = -1
            elif direction == 1:
                trail = max(trail, close[i] - atr_v[i] * params["atr_trail"])
                if close[i] < trail or bear_cross:
                    direction = 0
                else:
                    pos[i] = 1
            else:  # direction == -1
                trail = min(trail, close[i] + atr_v[i] * params["atr_trail"])
                if close[i] > trail or bull_cross:
                    direction = 0
                else:
                    pos[i] = -1

    elif strategy == "mean_reversion":
        bb_mid, bb_up, bb_lo = _bb(close, params["bb_len"], params["bb_std"])
        rsi_v = _rsi(close, 14)
        atr_v = _atr(high, low, close, 14)
        vol_ma = _sma(volume, 20)
        adx_v = _adx(high, low, close, 14)

        vol_mult = params.get("vol_mult", 1.0)
        sl_mult = params.get("sl_mult", 1.5)
        max_hold = params.get("max_hold", 16)
        adx_max = params.get("adx_max", 25)
        direction = 0
        sl_level = 0.0
        bars_held = 0
        for i in range(1, n):
            if np.isnan(bb_lo[i]) or np.isnan(rsi_v[i]) or np.isnan(vol_ma[i]) or np.isnan(atr_v[i]) or np.isnan(adx_v[i]):
                continue
            vol_ok = vol_ma[i] > 0 and volume[i] > vol_ma[i] * vol_mult
            adx_ok = adx_v[i] < adx_max

            if direction == 0:
                if close[i] <= bb_lo[i] and rsi_v[i] < params["rsi_os"] and vol_ok and adx_ok:
                    direction = 1
                    sl_level = close[i] - atr_v[i] * sl_mult
                    pos[i] = 1
                    bars_held = 0
                elif close[i] >= bb_up[i] and rsi_v[i] > params["rsi_ob"] and vol_ok and adx_ok:
                    direction = -1
                    sl_level = close[i] + atr_v[i] * sl_mult
                    pos[i] = -1
                    bars_held = 0
            elif direction == 1:
                bars_held += 1
                if close[i] < sl_level or close[i] >= bb_mid[i] or bars_held >= max_hold:
                    direction = 0
                else:
                    pos[i] = 1
            else:  # direction == -1
                bars_held += 1
                if close[i] > sl_level or close[i] <= bb_mid[i] or bars_held >= max_hold:
                    direction = 0
                else:
                    pos[i] = -1

    elif strategy == "swing_momentum":
        rsi_v = _rsi(close, params["rsi_len"])
        atr_v = _atr(high, low, close, 14)
        vol_ma = _sma(volume, 20)
        ema_t = _ema(close, params["ema_len"])

        rsi_bull = params.get("rsi_bull", 50)
        rsi_bear = params.get("rsi_bear", 50)
        direction = 0
        trail = 0.0
        for i in range(1, n):
            if np.isnan(rsi_v[i]) or np.isnan(atr_v[i]) or np.isnan(vol_ma[i]) or np.isnan(ema_t[i]):
                continue
            vol_ok = vol_ma[i] > 0 and volume[i] > vol_ma[i] * params["vol_thresh"]
            bull_rsi = rsi_v[i] > rsi_bull and rsi_v[i - 1] <= rsi_bull
            bear_rsi = rsi_v[i] < rsi_bear and rsi_v[i - 1] >= rsi_bear
            above = close[i] > ema_t[i]
            below = close[i] < ema_t[i]

            if direction == 0:
                if bull_rsi and vol_ok and above:
                    direction = 1
                    trail = close[i] - atr_v[i] * params["atr_trail"]
                    pos[i] = 1
                elif bear_rsi and vol_ok and below:
                    direction = -1
                    trail = close[i] + atr_v[i] * params["atr_trail"]
                    pos[i] = -1
            elif direction == 1:
                trail = max(trail, close[i] - atr_v[i] * params["atr_trail"])
                if close[i] < trail or bear_rsi:
                    direction = 0
                else:
                    pos[i] = 1
            else:  # direction == -1
                trail = min(trail, close[i] + atr_v[i] * params["atr_trail"])
                if close[i] > trail or bull_rsi:
                    direction = 0
                else:
                    pos[i] = -1

    elif strategy == "ema_trend":
        ema_f = _ema(close, params["ema_fast"])
        ema_s = _ema(close, params["ema_slow"])
        atr_v = _atr(high, low, close, 14)
        trail_mult = params["atr_trail"]
        direction = 0
        trail = 0.0
        for i in range(1, n):
            if np.isnan(ema_s[i]) or np.isnan(atr_v[i]):
                continue
            bull = ema_f[i] > ema_s[i]
            bear = ema_f[i] < ema_s[i]
            bull_x = bull and ema_f[i-1] <= ema_s[i-1]
            bear_x = bear and ema_f[i-1] >= ema_s[i-1]
            if direction == 0:
                if bull_x:
                    direction = 1; trail = close[i] - atr_v[i] * trail_mult; pos[i] = 1
                elif bear_x:
                    direction = -1; trail = close[i] + atr_v[i] * trail_mult; pos[i] = -1
            elif direction == 1:
                trail = max(trail, close[i] - atr_v[i] * trail_mult)
                if close[i] < trail or bear_x:
                    direction = -1 if bear_x else 0
                    if direction == -1:
                        trail = close[i] + atr_v[i] * trail_mult; pos[i] = -1
                else:
                    pos[i] = 1
            elif direction == -1:
                trail = min(trail, close[i] + atr_v[i] * trail_mult)
                if close[i] > trail or bull_x:
                    direction = 1 if bull_x else 0
                    if direction == 1:
                        trail = close[i] - atr_v[i] * trail_mult; pos[i] = 1
                else:
                    pos[i] = -1

    elif strategy == "rsi_momentum":
        rsi_v = _rsi(close, params["rsi_len"])
        ema_t = _ema(close, params["ema_len"])
        atr_v = _atr(high, low, close, 14)
        trail_mult = params["atr_trail"]
        direction = 0
        trail = 0.0
        for i in range(1, n):
            if np.isnan(rsi_v[i]) or np.isnan(ema_t[i]) or np.isnan(atr_v[i]):
                continue
            bull_cross = rsi_v[i] > 50 and rsi_v[i-1] <= 50
            bear_cross = rsi_v[i] < 50 and rsi_v[i-1] >= 50
            if direction == 0:
                if bull_cross and close[i] > ema_t[i]:
                    direction = 1; trail = close[i] - atr_v[i] * trail_mult; pos[i] = 1
                elif bear_cross and close[i] < ema_t[i]:
                    direction = -1; trail = close[i] + atr_v[i] * trail_mult; pos[i] = -1
            elif direction == 1:
                trail = max(trail, close[i] - atr_v[i] * trail_mult)
                if close[i] < trail:
                    direction = 0
                else:
                    pos[i] = 1
            elif direction == -1:
                trail = min(trail, close[i] + atr_v[i] * trail_mult)
                if close[i] > trail:
                    direction = 0
                else:
                    pos[i] = -1

    elif strategy == "macd_trend":
        s = pd.Series(close)
        macd_fast = s.ewm(span=params["macd_fast"], adjust=False).mean()
        macd_slow = s.ewm(span=params["macd_slow"], adjust=False).mean()
        macd_line = macd_fast - macd_slow
        macd_signal = macd_line.ewm(span=9, adjust=False).mean()
        hist = (macd_line - macd_signal).values
        ema_t = _ema(close, params["macd_slow"])
        atr_v = _atr(high, low, close, 14)
        trail_mult = params["atr_trail"]
        direction = 0
        trail = 0.0
        for i in range(1, n):
            if np.isnan(hist[i]) or np.isnan(ema_t[i]) or np.isnan(atr_v[i]):
                continue
            bull_cross = hist[i] > 0 and hist[i-1] <= 0
            bear_cross = hist[i] < 0 and hist[i-1] >= 0
            if direction == 0:
                if bull_cross and close[i] > ema_t[i]:
                    direction = 1; trail = close[i] - atr_v[i] * trail_mult; pos[i] = 1
                elif bear_cross and close[i] < ema_t[i]:
                    direction = -1; trail = close[i] + atr_v[i] * trail_mult; pos[i] = -1
            elif direction == 1:
                trail = max(trail, close[i] - atr_v[i] * trail_mult)
                if close[i] < trail:
                    direction = 0
                else:
                    pos[i] = 1
            elif direction == -1:
                trail = min(trail, close[i] + atr_v[i] * trail_mult)
                if close[i] > trail:
                    direction = 0
                else:
                    pos[i] = -1

    elif strategy == "breakout":
        dc_up, dc_lo, dc_mid = _donchian(high, low, params["dc_len"])
        atr_v = _atr(high, low, close, 14)
        adx_v = _adx(high, low, close, 14)
        vol_ma = _sma(volume, 20)
        lookback = 5
        min_inside = 3

        direction = 0
        sl_level = tp_level = 0.0
        for i in range(lookback + 1, n):
            if np.isnan(dc_up[i]) or np.isnan(adx_v[i]) or np.isnan(vol_ma[i]) or np.isnan(atr_v[i]):
                continue

            vol_ok = vol_ma[i] > 0 and volume[i] > vol_ma[i] * params["vol_thresh"]
            adx_rising = adx_v[i] > adx_v[max(0, i - 3)] and adx_v[i] >= 20
            inside_count = sum(
                1 for k in range(1, lookback + 1)
                if not np.isnan(dc_up[i - k]) and high[i - k] <= dc_up[i - k] and low[i - k] >= dc_lo[i - k]
            )
            consolidated = inside_count >= min_inside

            if direction == 0:
                if close[i] > dc_up[i - 1] and vol_ok and adx_rising and consolidated:
                    direction = 1
                    sl_level = close[i] - atr_v[i] * params["atr_sl"]
                    tp_level = close[i] + atr_v[i] * params["atr_tp"]
                    pos[i] = 1
                elif close[i] < dc_lo[i - 1] and vol_ok and adx_rising and consolidated:
                    direction = -1
                    sl_level = close[i] + atr_v[i] * params["atr_sl"]
                    tp_level = close[i] - atr_v[i] * params["atr_tp"]
                    pos[i] = -1
            elif direction == 1:
                if close[i] <= sl_level or close[i] >= tp_level:
                    direction = 0
                elif close[i] < dc_mid[i] or adx_v[i] < 14:
                    direction = 0
                else:
                    pos[i] = 1
            else:  # direction == -1
                if close[i] >= sl_level or close[i] <= tp_level:
                    direction = 0
                elif close[i] > dc_mid[i] or adx_v[i] < 14:
                    direction = 0
                else:
                    pos[i] = -1

    elif strategy == "accumulation":
        bb_mid, bb_up, bb_lo = _bb(close, params["bb_len"], 2.0)
        atr_v = _atr(high, low, close, 14)
        adx_v = _adx(high, low, close, 14)
        rsi_v = _rsi(close, 14)
        vol_ma = _sma(volume, 20)

        direction = 0
        sl_level = 0.0
        for i in range(1, n):
            if np.isnan(bb_up[i]) or np.isnan(adx_v[i]) or np.isnan(rsi_v[i]) or np.isnan(atr_v[i]) or np.isnan(vol_ma[i]):
                continue
            adx_low = adx_v[i] < params.get("adx_max", 25)
            vol_ok = vol_ma[i] > 0 and volume[i] > vol_ma[i] * 0.8

            if direction == 0:
                if adx_low and close[i] <= bb_lo[i] and rsi_v[i] < params["rsi_dip"] and vol_ok:
                    direction = 1
                    sl_level = close[i] - atr_v[i] * params["atr_sl"]
                    pos[i] = 1
                elif adx_low and close[i] >= bb_up[i] and rsi_v[i] > (100 - params["rsi_dip"]) and vol_ok:
                    direction = -1
                    sl_level = close[i] + atr_v[i] * params["atr_sl"]
                    pos[i] = -1
            elif direction == 1:
                if close[i] <= sl_level:
                    direction = 0
                elif close[i] >= bb_mid[i]:
                    direction = 0
                else:
                    pos[i] = 1
            else:  # direction == -1
                if close[i] >= sl_level:
                    direction = 0
                elif close[i] <= bb_mid[i]:
                    direction = 0
                else:
                    pos[i] = -1

    pct = np.zeros(n)
    pct[1:] = (close[1:] - close[:-1]) / close[:-1]
    strat_ret = np.roll(pos, 1) * pct
    strat_ret[0] = 0.0
    chg = np.abs(np.diff(pos, prepend=0))
    strat_ret -= chg * (fee_pct + slip_pct) / 100.0
    trades = int(np.sum(chg > 0))
    prev_pos = np.roll(pos, 1); prev_pos[0] = 0
    longs = int(np.sum((pos == 1) & (prev_pos != 1)))
    shorts = int(np.sum((pos == -1) & (prev_pos != -1)))
    return strat_ret, trades, longs, shorts, pos


# ── Performance Metrics ───────────────────────────────────────────────

def _metrics(returns: np.ndarray, ann_factor: float = 365) -> dict:
    total_ret = float(np.prod(1 + returns) - 1)
    std = float(np.std(returns))
    sharpe = float(np.mean(returns) / std * np.sqrt(ann_factor)) if std > 1e-10 else 0.0
    cum = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(cum)
    dd = np.where(peak > 0, (cum - peak) / peak, 0)
    max_dd = float(np.min(dd))
    return {
        "total_return": round(total_ret * 100, 1),
        "sharpe": round(sharpe, 2),
        "max_drawdown": round(max_dd * 100, 1),
    }


def _extract_trades(pos, close, dates, fee_pct, slip_pct, date_fmt):
    """Build a list of trade records from the position array."""
    trades = []
    n = len(pos)
    cost_per_side = (fee_pct + slip_pct) / 100.0
    entry_idx = None
    direction = 0

    for i in range(n):
        cur = int(pos[i])
        if cur != 0 and direction == 0:
            direction = cur
            entry_idx = i
        elif direction != 0 and cur != direction:
            exit_price = float(close[i])
            entry_price = float(close[entry_idx])
            gross = (exit_price - entry_price) / entry_price * direction * 100
            net = gross - cost_per_side * 2 * 100
            trades.append({
                "entry_date": dates[entry_idx].strftime(date_fmt),
                "exit_date": dates[i].strftime(date_fmt),
                "dir": "LONG" if direction == 1 else "SHORT",
                "entry": round(entry_price, 2),
                "exit": round(exit_price, 2),
                "pnl": round(net, 2),
                "bars": i - entry_idx,
            })
            if cur != 0:
                direction = cur
                entry_idx = i
            else:
                direction = 0
                entry_idx = None

    if direction != 0 and entry_idx is not None:
        exit_price = float(close[n - 1])
        entry_price = float(close[entry_idx])
        gross = (exit_price - entry_price) / entry_price * direction * 100
        net = gross - cost_per_side * 2 * 100
        trades.append({
            "entry_date": dates[entry_idx].strftime(date_fmt),
            "exit_date": dates[n - 1].strftime(date_fmt) + " (open)",
            "dir": "LONG" if direction == 1 else "SHORT",
            "entry": round(entry_price, 2),
            "exit": round(exit_price, 2),
            "pnl": round(net, 2),
            "bars": (n - 1) - entry_idx,
        })

    return trades


# ── Parameter Grids ──────────────────────────────────────────────────

_PULLBACK_GRID = [
    {"ema_slow": es, "ema_fast": ef, "vol_thresh": v, "atr_trail": t,
     "cooldown": cd, "max_hold": mh, "trend_lb": 12, "min_slope": ms, "adx_min": am}
    for es in (40, 50)
    for ef in (6, 8, 10)
    for v in (0.8, 1.0)
    for t in (0.8, 1.0, 1.5)
    for cd in (12, 24)
    for mh in (30, 48)
    for ms in (0.1, 0.2, 0.4)
    for am in (18, 22)
    if ef < es
]

_TREND_GRID = [
    {"ema_fast": f, "ema_mid": m, "ema_slow": s, "adx_thresh": a, "atr_trail": t}
    for f in (8, 10, 14)
    for m in (25, 30, 40)
    for s in (45, 50, 60)
    for a in (18, 22, 26)
    for t in (2.0, 2.5, 3.0, 3.5)
    if f < m < s
]

_MR_GRID = [
    {"bb_len": b, "bb_std": s, "rsi_os": o, "rsi_ob": ob,
     "vol_mult": vm, "sl_mult": sl, "max_hold": mh, "adx_max": am}
    for b in (20, 25, 30)
    for s in (1.8, 2.0, 2.2)
    for o in (28, 32, 36)
    for ob in (68, 72)
    for vm in (0.8, 1.0, 1.3)
    for sl in (1.5, 2.0)
    for mh in (12, 18, 24)
    for am in (20, 25)
]

_SWING_GRID = [
    {"rsi_len": r, "ema_len": e, "vol_thresh": v, "atr_trail": t,
     "rsi_bull": rb, "rsi_bear": rr}
    for r in (16, 18, 22)
    for e in (40, 50, 60)
    for v in (0.8, 1.0, 1.2)
    for t in (2.0, 2.5, 3.0, 3.5)
    for rb in (48, 50, 52)
    for rr in (50, 52)
]

_BREAKOUT_GRID = [
    {"dc_len": d, "vol_thresh": v, "atr_sl": s, "atr_tp": t}
    for d in (10, 15, 20, 25)
    for v in (1.0, 1.3, 1.5, 2.0)
    for s in (1.0, 1.5, 2.0)
    for t in (2.0, 3.0, 4.0)
]

_ACCUM_GRID = [
    {"bb_len": b, "rsi_dip": r, "atr_sl": s, "adx_max": am}
    for b in (15, 20, 30)
    for r in (30, 35, 40)
    for s in (1.0, 1.5, 2.0)
    for am in (20, 25, 30)
]

_EMA_TREND_GRID = [
    {"ema_fast": f, "ema_slow": s, "atr_trail": t}
    for f in (8, 10, 12, 15, 20)
    for s in (40, 50, 60)
    for t in (2.0, 2.5, 3.0, 3.5, 4.0, 5.0)
    if f < s
]

_RSI_MOMENTUM_GRID = [
    {"rsi_len": r, "ema_len": e, "atr_trail": t}
    for r in (14, 16, 18, 20, 24)
    for e in (40, 50, 60)
    for t in (3.0, 3.5, 4.0, 5.0)
]

_MACD_TREND_GRID = [
    {"macd_fast": f, "macd_slow": s, "atr_trail": t}
    for f in (8, 10, 12, 16)
    for s in (20, 26, 34)
    for t in (3.0, 3.5, 4.0, 5.0)
    if f < s
]

_STRATEGY_GRIDS = {
    "ema_trend": _EMA_TREND_GRID,
    "rsi_momentum": _RSI_MOMENTUM_GRID,
    "macd_trend": _MACD_TREND_GRID,
    # Legacy
    "pullback": _PULLBACK_GRID,
    "trend_following": _TREND_GRID,
    "mean_reversion": _MR_GRID,
    "swing_momentum": _SWING_GRID,
    "breakout": _BREAKOUT_GRID,
    "accumulation": _ACCUM_GRID,
}


def _optimize(close, high, low, volume, strategy, fee, slip, ann_factor=365):
    """Grid-search for highest-Sharpe parameter set."""
    grid = _STRATEGY_GRIDS.get(strategy, _RSI_MOMENTUM_GRID)

    best_sharpe, best_params = -np.inf, grid[0]
    for p in grid:
        r, *_ = _execute(close, high, low, volume, strategy, p, fee, slip)
        s = np.std(r)
        sh = np.mean(r) / s * np.sqrt(ann_factor) if s > 1e-10 else 0
        if sh > best_sharpe:
            best_sharpe, best_params = sh, p
    return dict(best_params), round(float(best_sharpe), 2)


# ── Binance Data Download ────────────────────────────────────────────

def _fetch_binance(symbol: str, start: str, end: str, timeframe: str = "1d"):
    """Download OHLCV from Binance via ccxt (no API key needed)."""
    import ccxt

    ccxt_sym = symbol
    for quote in ("USDT", "BUSD", "BTC", "USD"):
        if symbol.upper().endswith(quote):
            ccxt_sym = symbol[: -len(quote)] + "/" + quote
            break

    exchange = ccxt.binance({"enableRateLimit": True})
    since_ms = int(pd.Timestamp(start).timestamp() * 1000)
    end_ms = int(pd.Timestamp(end).timestamp() * 1000)

    all_rows: list = []
    while since_ms < end_ms:
        ohlcv = exchange.fetch_ohlcv(ccxt_sym, timeframe, since=since_ms, limit=1000)
        if not ohlcv:
            break
        all_rows.extend(ohlcv)
        since_ms = ohlcv[-1][0] + 1
        if len(ohlcv) < 1000:
            break

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows, columns=["ts", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("Date").drop(columns=["ts"])
    df = df[~df.index.duplicated(keep="first")]
    df = df[df.index < pd.Timestamp(end, tz="UTC")]
    return df


# ── Cached Data Layer ────────────────────────────────────────────────

def _get_ohlcv(symbol: str, start: str, end: str, timeframe: str) -> pd.DataFrame:
    """Get OHLCV data, using MongoDB cache and downloading only missing ranges."""
    from agent_platform.db.ohlcv_cache import (
        get_cached_range, load_cached, store_ohlcv, _TF_DELTA,
    )

    req_start = pd.Timestamp(start, tz="UTC")
    req_end = pd.Timestamp(end, tz="UTC")
    tf_delta = _TF_DELTA.get(timeframe, pd.Timedelta(days=1))

    cached_start, cached_end, count = get_cached_range(symbol, timeframe)

    if count > 0 and cached_start is not None and cached_end is not None:
        need_before = req_start < cached_start
        need_after = req_end > cached_end + tf_delta

        if not need_before and not need_after:
            logger.info("Cache hit for %s/%s [%s → %s] (%d candles)",
                        symbol, timeframe, start, end, count)
            return load_cached(symbol, timeframe, start, end)

        if need_before:
            end_str = cached_start.strftime("%Y-%m-%dT%H:%M:%S")
            logger.info("Filling start gap %s/%s [%s → %s]", symbol, timeframe, start, end_str)
            df_pre = _fetch_binance(symbol, start, end_str, timeframe)
            if not df_pre.empty:
                df_pre = df_pre[df_pre.index < cached_start]
                if not df_pre.empty:
                    store_ohlcv(symbol, timeframe, df_pre)

        if need_after:
            next_ms = int(cached_end.timestamp() * 1000) + 1
            start_after = pd.Timestamp(next_ms, unit="ms", tz="UTC")
            start_str = start_after.strftime("%Y-%m-%dT%H:%M:%S")
            logger.info("Filling end gap %s/%s [%s → %s]", symbol, timeframe, start_str, end)
            df_post = _fetch_binance(symbol, start_str, end, timeframe)
            if not df_post.empty:
                df_post = df_post[df_post.index > cached_end]
                if not df_post.empty:
                    store_ohlcv(symbol, timeframe, df_post)
    else:
        logger.info("No cache for %s/%s, downloading [%s → %s]", symbol, timeframe, start, end)
        df_full = _fetch_binance(symbol, start, end, timeframe)
        if not df_full.empty:
            store_ohlcv(symbol, timeframe, df_full)

    return load_cached(symbol, timeframe, start, end)


# ── Walk-Forward Engine ──────────────────────────────────────────────

def _walk_forward(cfg: dict):
    """Generator yielding SSE events: info → fold × N → complete."""
    try:
        import ccxt  # noqa: F401
    except ImportError:
        yield {"type": "error", "message": "ccxt not installed. Run: pip install ccxt"}
        return

    ticker = cfg.get("ticker", "BTCUSDT")
    start = cfg.get("start", "2021-01-01")
    end = cfg.get("end", "2026-01-01")
    train_days = int(cfg.get("train_days", 180))
    test_days = int(cfg.get("test_days", 30))
    strategy = cfg.get("strategy", "trend_following")
    fee = float(cfg.get("exchange_fee", 0.04))
    slip = float(cfg.get("slippage", 0.01))

    if strategy not in _STRATEGY_TIMEFRAMES:
        yield {
            "type": "error",
            "message": (
                f"Strategy \"{strategy}\" does not have a Python walk-forward implementation. "
                "Supported strategies: EMA Trend, RSI Momentum, MACD Trend, "
                "plus legacy: Trend Following, Mean Reversion, Swing Momentum, "
                "Pullback, Breakout, Accumulation."
            ),
        }
        return

    timeframe = _STRATEGY_TIMEFRAMES.get(strategy, "1d")
    ann_factor = _PERIODS_PER_YEAR.get(timeframe, 365)
    date_fmt = "%Y-%m-%d %H:%M" if timeframe != "1d" else "%Y-%m-%d"

    try:
        df = _get_ohlcv(ticker, start, end, timeframe)
    except Exception as exc:
        yield {"type": "error", "message": f"Data load failed: {exc}"}
        return

    if df.empty:
        yield {"type": "error", "message": f"No data found for {ticker}"}
        return

    close = df["Close"].values.astype(float)
    high = df["High"].values.astype(float)
    low = df["Low"].values.astype(float)
    volume = df["Volume"].values.astype(float)
    dates = df.index

    train_delta = pd.Timedelta(days=train_days)
    test_delta = pd.Timedelta(days=test_days)

    folds = []
    cursor = dates[0]
    while True:
        train_end = cursor + train_delta
        test_end = train_end + test_delta
        if test_end > dates[-1]:
            break
        folds.append((cursor, train_end, test_end))
        cursor += test_delta

    total_folds = len(folds)
    if total_folds == 0:
        yield {"type": "error", "message": "Date range too short for walk-forward analysis"}
        return

    yield {
        "type": "info",
        "total_folds": total_folds,
        "data_points": len(df),
        "data_start": dates[0].strftime(date_fmt),
        "data_end": dates[-1].strftime(date_fmt),
        "timeframe": timeframe,
    }

    fold_results = []
    oos_returns_all = []
    oos_dates_all = []
    oos_trades_all = []
    oos_longs_total = 0
    oos_shorts_total = 0

    min_train_candles = 100
    min_test_candles = 20

    for idx, (train_start, train_end, test_end) in enumerate(folds):
        train_mask = (dates >= train_start) & (dates < train_end)
        test_mask = (dates >= train_end) & (dates < test_end)
        if train_mask.sum() < min_train_candles or test_mask.sum() < min_test_candles:
            continue

        try:
            best_params, train_sharpe = _optimize(
                close[train_mask], high[train_mask], low[train_mask],
                volume[train_mask], strategy, fee, slip, ann_factor,
            )
            oos_ret, oos_trades, oos_longs, oos_shorts, oos_pos = _execute(
                close[test_mask], high[test_mask], low[test_mask],
                volume[test_mask], strategy, best_params, fee, slip,
            )
            oos_met = _metrics(oos_ret, ann_factor)
            oos_fold_trades = _extract_trades(
                oos_pos, close[test_mask], dates[test_mask], fee, slip, date_fmt,
            )
        except Exception as exc:
            logger.exception("Fold %d failed", idx + 1)
            yield {"type": "fold_error", "fold_num": idx + 1, "message": str(exc)}
            continue

        oos_returns_all.extend(oos_ret.tolist())
        oos_dates_all.extend([d.strftime(date_fmt) for d in dates[test_mask]])
        oos_trades_all.extend(oos_fold_trades)
        oos_longs_total += oos_longs
        oos_shorts_total += oos_shorts

        fold_result = {
            "type": "fold",
            "fold_num": idx + 1,
            "total_folds": total_folds,
            "train_start": train_start.strftime("%Y-%m-%d"),
            "train_end": train_end.strftime("%Y-%m-%d"),
            "test_start": train_end.strftime("%Y-%m-%d"),
            "test_end": test_end.strftime("%Y-%m-%d"),
            "params": best_params,
            "train_sharpe": train_sharpe,
            "oos_return": oos_met["total_return"],
            "oos_trades": oos_trades,
        }
        fold_results.append(fold_result)
        yield fold_result

    if not fold_results:
        yield {"type": "error", "message": "No valid folds were computed"}
        return

    try:
        global_params, _ = _optimize(close, high, low, volume, strategy, fee, slip, ann_factor)
        is_ret, is_trades, is_longs, is_shorts, is_pos = _execute(
            close, high, low, volume, strategy, global_params, fee, slip,
        )
        is_met = _metrics(is_ret, ann_factor)
        is_met["trades"] = is_trades
        is_met["longs"] = is_longs
        is_met["shorts"] = is_shorts
        is_trade_list = _extract_trades(is_pos, close, dates, fee, slip, date_fmt)
    except Exception as exc:
        yield {"type": "error", "message": f"Global optimisation failed: {exc}"}
        return

    oos_arr = np.array(oos_returns_all)
    oos_met = _metrics(oos_arr, ann_factor)
    oos_met["trades"] = sum(f["oos_trades"] for f in fold_results)
    oos_met["longs"] = oos_longs_total
    oos_met["shorts"] = oos_shorts_total

    is_equity = np.cumprod(1 + is_ret).tolist()
    oos_equity = np.cumprod(1 + oos_arr).tolist()

    ret_deg = round(is_met["total_return"] - oos_met["total_return"], 1)
    sharpe_deg = round(is_met["sharpe"] - oos_met["sharpe"], 2)
    efficiency = (
        round(oos_met["sharpe"] / is_met["sharpe"] * 100)
        if abs(is_met["sharpe"]) > 0.01
        else 0
    )

    unique_param_sets = len({tuple(sorted(f["params"].items())) for f in fold_results})

    yield {
        "type": "complete",
        "strategy": strategy,
        "timeframe": timeframe,
        "is_metrics": is_met,
        "oos_metrics": oos_met,
        "is_params": global_params,
        "folds": fold_results,
        "is_equity": {
            "dates": [d.strftime(date_fmt) for d in dates],
            "values": is_equity,
        },
        "oos_equity": {
            "dates": oos_dates_all,
            "values": oos_equity,
        },
        "degradation": {
            "return": ret_deg,
            "sharpe": sharpe_deg,
            "efficiency": efficiency,
        },
        "unique_params": unique_param_sets,
        "is_trades_list": is_trade_list,
        "oos_trades_list": oos_trades_all,
    }


# ── Strategy CRUD ─────────────────────────────────────────────────────

class StrategyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    timeframe: str = Field(..., pattern=r"^(1m|3m|5m|15m|30m|1h|2h|4h|6h|8h|12h|1d|3d|1w)$")
    description: str = Field("", max_length=500)
    strategy_rules: str = Field("", max_length=2000)
    pine_script: str = Field(..., min_length=1)


@router.get("/strategies")
async def get_strategies():
    from agent_platform.db.repositories.strategy_repo import list_strategies
    strategies = await list_strategies()
    return {"strategies": strategies}


@router.post("/strategies", status_code=201)
async def create_strategy(body: StrategyCreate):
    from agent_platform.db.repositories.strategy_repo import create_strategy as _create
    strategy = await _create(
        name=body.name,
        timeframe=body.timeframe,
        description=body.description,
        strategy_rules=body.strategy_rules,
        pine_script=body.pine_script,
    )
    return strategy


@router.delete("/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str):
    from agent_platform.db.repositories.strategy_repo import delete_strategy as _delete
    deleted = await _delete(strategy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"ok": True}


# ── Run Endpoint ───────────────────────────────────────────────────────

@router.post("/run")
async def run_backtest(request: Request):
    cfg = await request.json()

    def generate():
        for event in _walk_forward(cfg):
            yield f"data: {_dumps(event)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
