#!/usr/bin/env python3
"""
Walk-Forward Backtest Runner — Iteration 4
===========================================
RADICAL SIMPLIFICATION: each strategy has only 2-3 free parameters.
Tiny grids make overfitting nearly impossible. 180-day train windows.
Dropped Pullback (never worked). 3-strategy portfolio on 4H.
"""

import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

SYMBOL = "BTC/USDT"
START_DATE = "2024-04-05"
END_DATE = "2026-04-05"
FEE_PCT = 0.04
SLIP_PCT = 0.01
CACHE_DIR = Path(__file__).parent / "data" / "outputs"

AF_4H = 6 * 365  # annualization factor for 4H bars


# ── Indicators ────────────────────────────────────────────────────────

def _rma(s, p):
    return pd.Series(s).ewm(alpha=1.0/p, min_periods=p, adjust=False).mean().values

def _ema(c, p):
    return pd.Series(c).ewm(span=p, adjust=False).mean().values

def _rsi(c, p=14):
    d = np.diff(c, prepend=c[0])
    g = np.where(d > 0, d, 0.0)
    l = np.where(d < 0, -d, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = _rma(g, p) / _rma(l, p)
    return 100.0 - 100.0 / (1.0 + rs)

def _atr(h, l, c, p=14):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return _rma(tr, p)

def _bb(c, p=20, ns=2.0):
    s = pd.Series(c)
    mid = s.rolling(p, min_periods=p).mean()
    std = s.rolling(p, min_periods=p).std()
    return mid.values, (mid + ns * std).values, (mid - ns * std).values

def _adx(h, l, c, p=14):
    ph = np.roll(h, 1); ph[0] = h[0]
    pl = np.roll(l, 1); pl[0] = l[0]
    pc = np.roll(c, 1); pc[0] = c[0]
    up = h - ph; dn = pl - l
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr_s = _rma(tr, p)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100.0 * _rma(pdm, p) / atr_s
        mdi = 100.0 * _rma(mdm, p) / atr_s
        dx = 100.0 * np.abs(pdi - mdi) / (pdi + mdi)
    return _rma(dx, p), pdi, mdi


# ── Data ──────────────────────────────────────────────────────────────

def fetch_ohlcv(symbol, timeframe, start, end):
    cache_file = CACHE_DIR / f"{symbol.replace('/', '_')}_{timeframe}_{start}_{end}.csv"
    if cache_file.exists():
        df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
        print(f"  [{timeframe}] {len(df)} cached bars")
        return df
    import ccxt
    ex = ccxt.binance({"enableRateLimit": True})
    since = int(pd.Timestamp(start).timestamp() * 1000)
    end_ms = int(pd.Timestamp(end).timestamp() * 1000)
    rows = []
    print(f"  [{timeframe}] Fetching {symbol}...", end=" ", flush=True)
    while since < end_ms:
        ohlcv = ex.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not ohlcv: break
        rows.extend(ohlcv)
        since = ohlcv[-1][0] + 1
        if len(ohlcv) < 1000: break
        time.sleep(0.1)
    df = pd.DataFrame(rows, columns=["ts", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("Date").drop(columns=["ts"])
    df = df[~df.index.duplicated(keep="first")]
    df = df[df.index < pd.Timestamp(end, tz="UTC")]
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_file)
    print(f"{len(df)} bars")
    return df


# ══════════════════════════════════════════════════════════════════════
# Strategy 1: EMA Trend (4H) — 3 parameters
# ══════════════════════════════════════════════════════════════════════
# Enter when EMA fast > slow (long) or fast < slow (short).
# Hold until EMA cross against OR ATR trailing stop hit.
# No ADX, no MACD, no DI. Pure price action.

def strat_ema_trend(close, high, low, volume, params):
    n = len(close)
    pos = np.zeros(n)
    ef = _ema(close, params["ema_fast"])
    es = _ema(close, params["ema_slow"])
    av = _atr(high, low, close, 14)
    trail_mult = params["atr_trail"]

    direction = 0; trail = 0.0
    for i in range(1, n):
        if np.isnan(es[i]) or np.isnan(av[i]):
            continue
        bull = ef[i] > es[i]
        bear = ef[i] < es[i]
        bull_x = bull and ef[i-1] <= es[i-1]
        bear_x = bear and ef[i-1] >= es[i-1]

        if direction == 0:
            if bull_x:
                direction = 1; trail = close[i] - av[i] * trail_mult; pos[i] = 1
            elif bear_x:
                direction = -1; trail = close[i] + av[i] * trail_mult; pos[i] = -1
        elif direction == 1:
            trail = max(trail, close[i] - av[i] * trail_mult)
            if close[i] < trail or bear_x:
                direction = -1 if bear_x else 0
                if direction == -1:
                    trail = close[i] + av[i] * trail_mult; pos[i] = -1
            else:
                pos[i] = 1
        elif direction == -1:
            trail = min(trail, close[i] + av[i] * trail_mult)
            if close[i] > trail or bull_x:
                direction = 1 if bull_x else 0
                if direction == 1:
                    trail = close[i] - av[i] * trail_mult; pos[i] = 1
            else:
                pos[i] = -1
    return pos

EMA_TREND_GRID = [
    {"ema_fast": f, "ema_slow": s, "atr_trail": t}
    for f in (8, 10, 12, 15, 20)
    for s in (30, 40, 50, 60)
    for t in (2.0, 2.5, 3.0, 3.5, 4.0, 5.0)
    if f < s
]


# ══════════════════════════════════════════════════════════════════════
# Strategy 2: RSI Momentum (4H) — 3 parameters
# ══════════════════════════════════════════════════════════════════════
# Enter long on RSI crossing above 50 with price > EMA.
# Enter short on RSI crossing below 50 with price < EMA.
# Exit on trailing stop or opposite RSI cross.

def strat_rsi_momentum(close, high, low, volume, params):
    n = len(close)
    pos = np.zeros(n)
    rv = _rsi(close, params["rsi_len"])
    et = _ema(close, params["ema_len"])
    av = _atr(high, low, close, 14)
    trail_mult = params["atr_trail"]

    direction = 0; trail = 0.0
    for i in range(1, n):
        if np.isnan(rv[i]) or np.isnan(et[i]) or np.isnan(av[i]):
            continue
        bull_cross = rv[i] > 50 and rv[i-1] <= 50
        bear_cross = rv[i] < 50 and rv[i-1] >= 50
        above_ema = close[i] > et[i]
        below_ema = close[i] < et[i]

        if direction == 0:
            if bull_cross and above_ema:
                direction = 1; trail = close[i] - av[i] * trail_mult; pos[i] = 1
            elif bear_cross and below_ema:
                direction = -1; trail = close[i] + av[i] * trail_mult; pos[i] = -1
        elif direction == 1:
            trail = max(trail, close[i] - av[i] * trail_mult)
            if close[i] < trail or bear_cross:
                direction = 0
            else:
                pos[i] = 1
        elif direction == -1:
            trail = min(trail, close[i] + av[i] * trail_mult)
            if close[i] > trail or bull_cross:
                direction = 0
            else:
                pos[i] = -1
    return pos

RSI_MOMENTUM_GRID = [
    {"rsi_len": r, "ema_len": e, "atr_trail": t}
    for r in (12, 14, 16, 18, 20, 24)
    for e in (30, 40, 50, 60)
    for t in (2.0, 2.5, 3.0, 3.5, 4.0, 5.0)
]


# ══════════════════════════════════════════════════════════════════════
# Strategy 3a: Trend Dip (4H) — 3 parameters
# ══════════════════════════════════════════════════════════════════════
# Buy the dip in an uptrend: when EMA(slow) is rising and RSI dips
# below threshold then recovers, enter long. Vice versa for shorts.
# Complementary: enters on pullbacks, not trend starts like EMA/RSI.

def strat_trend_dip(close, high, low, volume, params):
    n = len(close)
    pos = np.zeros(n)
    es = _ema(close, params["ema_len"])
    rv = _rsi(close, 14)
    av = _atr(high, low, close, 14)
    trail_mult = params["atr_trail"]
    rsi_dip = params["rsi_dip"]  # e.g. 35

    slope_lb = 10
    direction = 0; trail = 0.0; was_dipped = False; was_spiked = False

    for i in range(slope_lb + 1, n):
        if np.isnan(es[i]) or np.isnan(rv[i]) or np.isnan(av[i]):
            continue
        slope = (es[i] - es[i - slope_lb]) / es[i - slope_lb] * 100
        uptrend = slope > 0.1
        downtrend = slope < -0.1

        if rv[i] < rsi_dip:
            was_dipped = True
        if rv[i] > (100 - rsi_dip):
            was_spiked = True

        if direction == 0:
            if uptrend and was_dipped and rv[i] > rsi_dip and rv[i-1] <= rsi_dip:
                direction = 1; trail = close[i] - av[i] * trail_mult
                pos[i] = 1; was_dipped = False
            elif downtrend and was_spiked and rv[i] < (100 - rsi_dip) and rv[i-1] >= (100 - rsi_dip):
                direction = -1; trail = close[i] + av[i] * trail_mult
                pos[i] = -1; was_spiked = False
        elif direction == 1:
            trail = max(trail, close[i] - av[i] * trail_mult)
            if close[i] < trail or not uptrend:
                direction = 0
            else:
                pos[i] = 1
        elif direction == -1:
            trail = min(trail, close[i] + av[i] * trail_mult)
            if close[i] > trail or not downtrend:
                direction = 0
            else:
                pos[i] = -1
    return pos

TREND_DIP_GRID = [
    {"ema_len": e, "rsi_dip": r, "atr_trail": t}
    for e in (30, 40, 50, 60)
    for r in (30, 33, 36, 40)
    for t in (2.0, 2.5, 3.0, 3.5, 4.0, 5.0)
]


# ══════════════════════════════════════════════════════════════════════
# Strategy 3b: MACD Trend (4H) — 3 parameters
# ══════════════════════════════════════════════════════════════════════
# Enter on MACD histogram turning positive (long) or negative (short)
# when price is on the correct side of EMA.
# Simple, few parameters, captures momentum shifts differently than RSI.

def strat_macd_trend(close, high, low, volume, params):
    n = len(close)
    pos = np.zeros(n)
    ss = pd.Series(close)
    fast = ss.ewm(span=params["macd_fast"], adjust=False).mean()
    slow = ss.ewm(span=params["macd_slow"], adjust=False).mean()
    macd = fast - slow
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = (macd - signal).values
    et = _ema(close, params["macd_slow"])
    av = _atr(high, low, close, 14)
    trail_mult = params["atr_trail"]

    direction = 0; trail = 0.0
    for i in range(1, n):
        if np.isnan(hist[i]) or np.isnan(et[i]) or np.isnan(av[i]):
            continue
        bull_cross = hist[i] > 0 and hist[i-1] <= 0
        bear_cross = hist[i] < 0 and hist[i-1] >= 0

        if direction == 0:
            if bull_cross and close[i] > et[i]:
                direction = 1; trail = close[i] - av[i] * trail_mult; pos[i] = 1
            elif bear_cross and close[i] < et[i]:
                direction = -1; trail = close[i] + av[i] * trail_mult; pos[i] = -1
        elif direction == 1:
            trail = max(trail, close[i] - av[i] * trail_mult)
            if close[i] < trail or bear_cross:
                direction = 0
            else:
                pos[i] = 1
        elif direction == -1:
            trail = min(trail, close[i] + av[i] * trail_mult)
            if close[i] > trail or bull_cross:
                direction = 0
            else:
                pos[i] = -1
    return pos

MACD_GRID = [
    {"macd_fast": f, "macd_slow": s, "atr_trail": t}
    for f in (8, 10, 12, 16)
    for s in (20, 26, 34)
    for t in (2.0, 2.5, 3.0, 3.5, 4.0, 5.0)
    if f < s
]


# ── Engine ────────────────────────────────────────────────────────────

def compute_returns(pos, close):
    n = len(close)
    pct = np.zeros(n)
    pct[1:] = (close[1:] - close[:-1]) / close[:-1]
    sr = np.roll(pos, 1) * pct
    sr[0] = 0.0
    chg = np.abs(np.diff(pos, prepend=0))
    sr -= chg * (FEE_PCT + SLIP_PCT) / 100.0
    return sr

def compute_metrics(returns, ann_factor):
    if len(returns) == 0:
        return {"ret": 0, "sharpe": 0, "mdd": 0}
    tr = float(np.prod(1 + returns) - 1)
    std = float(np.std(returns))
    sh = float(np.mean(returns) / std * np.sqrt(ann_factor)) if std > 1e-10 else 0.0
    cum = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(cum)
    dd = np.where(peak > 0, (cum - peak) / peak, 0)
    mdd = float(np.min(dd))
    return {"ret": round(tr*100, 2), "sharpe": round(sh, 3), "mdd": round(mdd*100, 2)}

def extract_trades(pos, close, dates=None):
    trades = []
    n = len(pos)
    eidx = None; d = 0
    cost_rt = (FEE_PCT + SLIP_PCT) * 2 / 100.0
    for i in range(n):
        c = int(pos[i])
        if c != 0 and d == 0:
            d = c; eidx = i
        elif d != 0 and c != d:
            if eidx is not None:
                ep = close[eidx]; xp = close[i]
                gross = (xp - ep) / ep * d * 100
                trade = {"dir": "L" if d == 1 else "S", "entry": round(ep, 1),
                         "exit": round(xp, 1), "pnl": round(gross - cost_rt*100, 2),
                         "bars": i - eidx}
                if dates is not None:
                    trade["entry_date"] = str(dates[eidx])[:10]
                trades.append(trade)
            d = c if c != 0 else 0
            eidx = i if c != 0 else None
    return trades


# ── Walk-Forward Engine ───────────────────────────────────────────────

def grid_optimize(close, high, low, volume, fn, grid, af):
    best_sh = -np.inf
    best_p = grid[0]
    for p in grid:
        pos = fn(close, high, low, volume, p)
        ret = compute_returns(pos, close)
        s = np.std(ret)
        sh = np.mean(ret) / s * np.sqrt(af) if s > 1e-10 else 0
        if sh > best_sh:
            best_sh = sh; best_p = p
    return dict(best_p), float(best_sh)


def walk_forward(name, tf, fn, grid, df, train_days, test_days, af):
    c = df["Close"].values.astype(float)
    h = df["High"].values.astype(float)
    l = df["Low"].values.astype(float)
    v = df["Volume"].values.astype(float)
    dates = df.index

    folds = []
    cursor = dates[0]
    while True:
        te = cursor + pd.Timedelta(days=train_days)
        xe = te + pd.Timedelta(days=test_days)
        if xe > dates[-1]: break
        folds.append((cursor, te, xe))
        cursor += pd.Timedelta(days=test_days)

    nf = len(folds)
    print(f"\n{'='*72}")
    print(f"  WF: {name} ({tf}) | {len(df)} bars | {dates[0].date()} → {dates[-1].date()}")
    print(f"  Train={train_days}d Test={test_days}d Folds={nf} Grid={len(grid)} Params={len(grid[0])}")
    print(f"{'='*72}")

    oos_ret = []; oos_dt = []; fps = []; oos_tr = []

    for idx, (ts, te, xe) in enumerate(folds):
        trm = (dates >= ts) & (dates < te)
        ttm = (dates >= te) & (dates < xe)
        if trm.sum() < 60 or ttm.sum() < 10: continue

        bp, tsh = grid_optimize(c[trm], h[trm], l[trm], v[trm], fn, grid, af)
        tp = fn(c[ttm], h[ttm], l[ttm], v[ttm], bp)
        tr = compute_returns(tp, c[ttm])
        tm = compute_metrics(tr, af)

        oos_ret.extend(tr.tolist())
        oos_dt.extend(dates[ttm].tolist())
        fps.append(bp)
        oos_tr.extend(extract_trades(tp, c[ttm], dates[ttm]))

        nt = sum(1 for x in np.abs(np.diff(tp, prepend=0)) if x > 0)
        print(f"  Fold {idx+1:>2}/{nf} | Train Sh {tsh:>6.3f} | "
              f"OOS {tm['ret']:>7.2f}% | T={nt:>3} | Params={bp}",
              end="\r" if idx < nf-1 else "\n", flush=True)

    if not oos_ret:
        print("  NO VALID FOLDS"); return None

    oos_arr = np.array(oos_ret)
    oos_met = compute_metrics(oos_arr, af)
    oos_da = np.array(oos_dt)

    isp, _ = grid_optimize(c, h, l, v, fn, grid, af)
    ip = fn(c, h, l, v, isp)
    is_met = compute_metrics(compute_returns(ip, c), af)
    is_tr = extract_trades(ip, c, dates)

    print(f"\n  ── In-Sample ──")
    print(f"  Ret={is_met['ret']:>7.1f}%  Sh={is_met['sharpe']:>6.3f}  MDD={is_met['mdd']:>6.1f}%  "
          f"T={len(is_tr)}  P={isp}")
    print(f"\n  ── Out-of-Sample ──")
    print(f"  Ret={oos_met['ret']:>7.1f}%  Sh={oos_met['sharpe']:>6.3f}  MDD={oos_met['mdd']:>6.1f}%  T={len(oos_tr)}")

    eff = round(oos_met["sharpe"]/is_met["sharpe"]*100) if abs(is_met["sharpe"]) > 0.01 else 0
    print(f"  Degradation: {round(is_met['ret']-oos_met['ret'],1):+.1f}pp  Sh {round(is_met['sharpe']-oos_met['sharpe'],3):+.3f}  Eff={eff}%")

    yrs = sorted(set(d.year for d in oos_da))
    yr = {}
    print(f"\n  ── OOS Per-Year ──")
    for y in yrs:
        mask = np.array([d.year == y for d in oos_da])
        if mask.sum() < 30:
            print(f"    {y}: {mask.sum()} bars — skip"); continue
        ym = compute_metrics(oos_arr[mask], af)
        yt = [t for t in oos_tr if t.get("entry_date","").startswith(str(y))]
        yr[y] = ym
        print(f"    {y}: Ret={ym['ret']:>7.1f}%  Sh={ym['sharpe']:>6.3f}  MDD={ym['mdd']:>6.1f}%  T={len(yt)}")

    if oos_tr:
        w = [t for t in oos_tr if t["pnl"] > 0]
        lo = [t for t in oos_tr if t["pnl"] <= 0]
        wr = len(w)/len(oos_tr)*100
        aw = np.mean([t["pnl"] for t in w]) if w else 0
        al = np.mean([t["pnl"] for t in lo]) if lo else 0
        ab = np.mean([t["bars"] for t in oos_tr])
        print(f"  Trades: WR={wr:.1f}% AvgW={aw:.2f}% AvgL={al:.2f}% AvgHold={ab:.1f}bars")

    up = len({tuple(sorted(p.items())) for p in fps})
    print(f"  Param stability: {up} unique / {len(fps)} folds")

    issues = []
    if oos_met["sharpe"] < 0.5: issues.append(f"OOS Sh {oos_met['sharpe']:.3f} < 0.5")
    for y, ym in yr.items():
        if ym["sharpe"] < -0.5: issues.append(f"{y} Sh {ym['sharpe']:.3f}")
    if len(oos_tr) < 15: issues.append(f"Only {len(oos_tr)} trades")
    if oos_met["mdd"] < -30: issues.append(f"MDD {oos_met['mdd']:.1f}%")
    if oos_met["ret"] < 0: issues.append(f"Neg return {oos_met['ret']:.1f}%")

    tag = "PASS" if not issues else "REVIEW"
    print(f"\n  [{tag}]", "; ".join(issues) if issues else "All criteria met!")

    return {
        "name": name, "tf": tf,
        "is_met": is_met, "is_params": isp, "is_trades": len(is_tr),
        "oos_met": oos_met, "oos_trades": len(oos_tr),
        "yr": yr, "eff": eff, "param_unique": up,
        "total_folds": len(fps), "issues": issues,
    }


def main():
    print("=" * 72)
    print("  Walk-Forward Backtest Runner — Iteration 4 (Radical Simplification)")
    print(f"  {START_DATE} → {END_DATE} | Fees {FEE_PCT}%+{SLIP_PCT}%")
    print(f"  Strategy design: 2-3 free params each, tiny grids, anti-overfit")
    print("=" * 72)

    d4 = fetch_ohlcv(SYMBOL, "4h", START_DATE, END_DATE)
    print(f"4H bars: {len(d4)}")

    print(f"\nGrids: EMA_Trend={len(EMA_TREND_GRID)}, RSI_Mom={len(RSI_MOMENTUM_GRID)}, "
          f"TrendDip={len(TREND_DIP_GRID)}, MACD={len(MACD_GRID)}")

    results = []
    results.append(walk_forward(
        "EMA Trend", "4h", strat_ema_trend, EMA_TREND_GRID, d4,
        train_days=180, test_days=30, af=AF_4H
    ))
    results.append(walk_forward(
        "RSI Momentum", "4h", strat_rsi_momentum, RSI_MOMENTUM_GRID, d4,
        train_days=180, test_days=30, af=AF_4H
    ))
    results.append(walk_forward(
        "Trend Dip", "4h", strat_trend_dip, TREND_DIP_GRID, d4,
        train_days=180, test_days=30, af=AF_4H
    ))
    results.append(walk_forward(
        "MACD Trend", "4h", strat_macd_trend, MACD_GRID, d4,
        train_days=180, test_days=30, af=AF_4H
    ))

    # Portfolio — equal-weight all strategies
    print(f"\n{'='*72}")
    print(f"  EQUAL-WEIGHT PORTFOLIO (combined OOS equity curves)")
    print(f"{'='*72}")

    print(f"\n{'='*72}")
    print(f"  WALK-FORWARD SUMMARY — Iteration 4")
    print(f"{'='*72}")
    print(f"  {'Strategy':>20s} | {'IS Sh':>6s} {'OOS Sh':>7s} {'Eff%':>5s} | "
          f"{'OOS Ret':>8s} {'MDD':>7s} {'T':>4s} | Verdict")
    print(f"  {'-'*20}-+-{'-'*6}-{'-'*7}-{'-'*5}-+-{'-'*8}-{'-'*7}-{'-'*4}-+--------")
    all_ok = True
    for r in results:
        if r is None:
            print(f"  {'?':>20s} | FAILED"); all_ok = False; continue
        tag = "PASS" if not r["issues"] else "REVIEW"
        if r["issues"]: all_ok = False
        print(f"  {r['name']:>20s} | {r['is_met']['sharpe']:>6.3f} {r['oos_met']['sharpe']:>7.3f} "
              f"{r['eff']:>4d}% | "
              f"{r['oos_met']['ret']:>7.1f}% {r['oos_met']['mdd']:>6.1f}% {r['oos_trades']:>4d} | [{tag}]")

    print(f"\n  {'ALL PASS' if all_ok else 'NEEDS ITERATION'}")
    return results

if __name__ == "__main__":
    results = main()
