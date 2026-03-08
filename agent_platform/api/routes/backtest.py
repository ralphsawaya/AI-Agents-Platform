"""Walk-Forward Analysis backtesting API — Binance spot edition.

Translates the Pine Script strategies (scalping, trend_following,
mean_reversion) from teams/trading_agents into Python and runs
walk-forward optimisation on OHLCV data fetched from Binance via ccxt.
"""

import json
import logging
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/backtest", tags=["backtest"])

_STRATEGY_TIMEFRAMES = {
    "scalping": "15m",
    "trend_following": "4h",
    "mean_reversion": "4h",
}

_PERIODS_PER_YEAR = {
    "15m": 4 * 24 * 365,
    "1h": 24 * 365,
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

def _ema(close: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(close).ewm(span=period, adjust=False).mean().values


def _sma(v: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(v).rolling(period, min_periods=period).mean().values


def _rsi(close: np.ndarray, period: int) -> np.ndarray:
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_g = pd.Series(gain).rolling(period, min_periods=period).mean().values
    avg_l = pd.Series(loss).rolling(period, min_periods=period).mean().values
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
    return pd.Series(tr).rolling(period, min_periods=period).mean().values


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
    atr_s = pd.Series(tr).rolling(period, min_periods=period).mean().values

    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100.0 * pd.Series(plus_dm).rolling(period, min_periods=period).mean().values / atr_s
        minus_di = 100.0 * pd.Series(minus_dm).rolling(period, min_periods=period).mean().values / atr_s
        dx = 100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di)

    adx_vals = pd.Series(dx).rolling(period, min_periods=period).mean().values
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
    """Run strategy and return (daily_returns, trade_count)."""
    n = len(close)
    pos = np.zeros(n, dtype=np.float64)

    if strategy == "scalping":
        ema_v = _ema(close, params["ema_len"])
        atr_v = _atr(high, low, close, 22)
        vwap_v = _vwap(high, low, close, volume, 20)
        rsi_v = _rsi(close, 10)
        vol_ma = _sma(volume, 35)

        held = False
        sl_level = tp_level = 0.0
        for i in range(1, n):
            if np.isnan(ema_v[i]) or np.isnan(vwap_v[i]) or np.isnan(rsi_v[i]) or np.isnan(vol_ma[i]) or np.isnan(atr_v[i]):
                continue
            if not held:
                vol_spike = vol_ma[i] > 0 and volume[i] > vol_ma[i] * params["vol_thresh"]
                if close[i] > vwap_v[i] and close[i] > ema_v[i] and vol_spike and rsi_v[i] > 50:
                    pos[i] = 1
                    held = True
                    sl_level = close[i] - atr_v[i] * params["atr_sl"]
                    tp_level = close[i] + atr_v[i] * params["atr_tp"]
            else:
                if close[i] <= sl_level or close[i] >= tp_level:
                    held = False
                elif close[i] < vwap_v[i] or close[i] < ema_v[i]:
                    held = False
                else:
                    pos[i] = 1

    elif strategy == "trend_following":
        ema_f = _ema(close, params["ema_fast"])
        ema_m = _ema(close, params["ema_mid"])
        adx_v = _adx(high, low, close, 14)
        macd_h = _macd(close)
        atr_v = _atr(high, low, close, 14)

        held = False
        trail = 0.0
        for i in range(1, n):
            if np.isnan(ema_f[i]) or np.isnan(ema_m[i]) or np.isnan(adx_v[i]) or np.isnan(macd_h[i]) or np.isnan(atr_v[i]):
                continue
            bull_cross = ema_f[i] > ema_m[i] and ema_f[i - 1] <= ema_m[i - 1]
            bear_cross = ema_f[i] < ema_m[i] and ema_f[i - 1] >= ema_m[i - 1]

            if not held:
                if bull_cross and adx_v[i] > params["adx_thresh"] and macd_h[i] > 0:
                    pos[i] = 1
                    held = True
                    trail = close[i] - atr_v[i] * params["atr_trail"]
            else:
                trail = max(trail, close[i] - atr_v[i] * params["atr_trail"])
                if close[i] < trail:
                    held = False
                elif bear_cross or (adx_v[i] < params["adx_thresh"] and ema_f[i] < ema_m[i]):
                    held = False
                else:
                    pos[i] = 1

    elif strategy == "mean_reversion":
        bb_mid, bb_up, bb_lo = _bb(close, params["bb_len"], params["bb_std"])
        rsi_v = _rsi(close, 14)
        atr_v = _atr(high, low, close, 14)
        vol_ma = _sma(volume, 20)

        held = False
        sl_level = 0.0
        for i in range(1, n):
            if np.isnan(bb_lo[i]) or np.isnan(rsi_v[i]) or np.isnan(vol_ma[i]) or np.isnan(atr_v[i]):
                continue
            if not held:
                vol_ok = vol_ma[i] > 0 and volume[i] > vol_ma[i] * 1.5
                if close[i] <= bb_lo[i] and rsi_v[i] < params["rsi_os"] and vol_ok:
                    pos[i] = 1
                    held = True
                    sl_level = close[i] - atr_v[i] * 1.5
            else:
                if close[i] < sl_level:
                    held = False
                elif close[i] >= bb_up[i] and rsi_v[i] > params["rsi_ob"]:
                    held = False
                elif close[i] >= bb_mid[i]:
                    held = False
                else:
                    pos[i] = 1

    pct = np.zeros(n)
    pct[1:] = (close[1:] - close[:-1]) / close[:-1]
    strat_ret = np.roll(pos, 1) * pct
    strat_ret[0] = 0.0
    chg = np.abs(np.diff(pos, prepend=0))
    strat_ret -= chg * (fee_pct + slip_pct) / 100.0
    trades = int(np.sum(chg > 0))
    return strat_ret, trades


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


# ── Parameter Grids ──────────────────────────────────────────────────

_SCALP_GRID = [
    {"ema_len": e, "vol_thresh": v, "atr_sl": s, "atr_tp": t}
    for e in (8, 10, 14, 20)
    for v in (2.0, 2.5, 3.0, 3.5)
    for s in (0.5, 0.75, 1.0)
    for t in (2.0, 3.0, 4.0)
]

_TREND_GRID = [
    {"ema_fast": f, "ema_mid": m, "adx_thresh": a, "atr_trail": t}
    for f in (5, 9, 13)
    for m in (15, 21, 30)
    for a in (20, 25, 30)
    for t in (1.5, 2.0, 2.5, 3.0)
    if f < m
]

_MR_GRID = [
    {"bb_len": b, "bb_std": s, "rsi_os": o, "rsi_ob": ob}
    for b in (15, 20, 25)
    for s in (1.5, 2.0, 2.5)
    for o in (25, 30, 35)
    for ob in (65, 70, 75)
]


def _optimize(close, high, low, volume, strategy, fee, slip, ann_factor=365):
    """Grid-search for highest-Sharpe parameter set."""
    if strategy == "scalping":
        grid = _SCALP_GRID
    elif strategy == "trend_following":
        grid = _TREND_GRID
    else:
        grid = _MR_GRID

    best_sharpe, best_params = -np.inf, grid[0]
    for p in grid:
        r, _ = _execute(close, high, low, volume, strategy, p, fee, slip)
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
    train_days = int(cfg.get("train_days", 90))
    test_days = int(cfg.get("test_days", 14))
    strategy = cfg.get("strategy", "scalping")
    fee = float(cfg.get("exchange_fee", 0.1))
    slip = float(cfg.get("slippage", 0.05))

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
            oos_ret, oos_trades = _execute(
                close[test_mask], high[test_mask], low[test_mask],
                volume[test_mask], strategy, best_params, fee, slip,
            )
            oos_met = _metrics(oos_ret, ann_factor)
        except Exception as exc:
            logger.exception("Fold %d failed", idx + 1)
            yield {"type": "fold_error", "fold_num": idx + 1, "message": str(exc)}
            continue

        oos_returns_all.extend(oos_ret.tolist())
        oos_dates_all.extend([d.strftime(date_fmt) for d in dates[test_mask]])

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
        is_ret, is_trades = _execute(close, high, low, volume, strategy, global_params, fee, slip)
        is_met = _metrics(is_ret, ann_factor)
        is_met["trades"] = is_trades
    except Exception as exc:
        yield {"type": "error", "message": f"Global optimisation failed: {exc}"}
        return

    oos_arr = np.array(oos_returns_all)
    oos_met = _metrics(oos_arr, ann_factor)
    oos_met["trades"] = sum(f["oos_trades"] for f in fold_results)

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
    }


# ── API Endpoint ──────────────────────────────────────────────────────

@router.post("/run")
async def run_backtest(request: Request):
    cfg = await request.json()

    def generate():
        for event in _walk_forward(cfg):
            yield f"data: {_dumps(event)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
