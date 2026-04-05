#!/usr/bin/env python3
"""
Elite BTC/USDC Strategy Backtester — Iteration 3
=================================================
Key changes: triple EMA alignment for trend following, internal ADX
filter for mean reversion (no external regime needed), swing momentum
replaces breakout, pullback fine-tuning.
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

PERIODS_PER_YEAR = {"15m": 4*24*365, "1h": 24*365, "2h": 12*365, "4h": 6*365}


# ── Indicators (TradingView RMA-based) ───────────────────────────────

def _rma(s, p):
    return pd.Series(s).ewm(alpha=1.0/p, min_periods=p, adjust=False).mean().values

def _ema(c, p):
    return pd.Series(c).ewm(span=p, adjust=False).mean().values

def _sma(v, p):
    return pd.Series(v).rolling(p, min_periods=p).mean().values

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
    return _rma(dx, p)

def _macd_hist(c, f=12, s=26, sg=9):
    ss = pd.Series(c)
    ml = ss.ewm(span=f, adjust=False).mean() - ss.ewm(span=s, adjust=False).mean()
    return (ml - ml.ewm(span=sg, adjust=False).mean()).values

def _donchian(h, l, p):
    u = pd.Series(h).rolling(p, min_periods=p).max().values
    lo = pd.Series(l).rolling(p, min_periods=p).min().values
    return u, lo, (u + lo) / 2.0


# ── Data Fetching ─────────────────────────────────────────────────────

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


# ── Regime Classifier ────────────────────────────────────────────────

def classify_regimes(h, l, c, v, params=None):
    p = params or {}
    adx_t = p.get("adx_trend", 22)
    n = len(c)
    adx_v = _adx(h, l, c, 14)
    ef = _ema(c, 9); em = _ema(c, 21); es = _ema(c, 50)
    atr_v = _atr(h, l, c, 14)
    bm, bu, bl = _bb(c, 20, 2.0)
    vm = _sma(v, 20)
    atr_p = np.where(c > 0, atr_v / c * 100, 0)
    bw = np.where(bm > 0, (bu - bl) / bm * 100, 0)
    vr = np.where(vm > 0, v / vm, 1.0)
    sl = np.zeros(n)
    sl[4:] = (es[4:] - es[:-4]) / np.where(es[:-4] != 0, es[:-4], 1) * 100
    regimes = np.full(n, "ranging", dtype=object)
    for i in range(50, n):
        if np.isnan(adx_v[i]) or np.isnan(bm[i]): continue
        if atr_p[i] > 2.5 and vr[i] > 1.5 and bw[i] > 4.0:
            regimes[i] = "volatile_breakout"
        elif adx_v[i] > adx_t and ef[i] > em[i] > es[i] and sl[i] > 0:
            regimes[i] = "uptrend"
        elif adx_v[i] > adx_t and ef[i] < em[i] < es[i] and sl[i] < 0:
            regimes[i] = "downtrend"
    return regimes

def _regime_mask(pos, regimes, allowed):
    f = pos.copy()
    for i in range(len(pos)):
        if regimes[i] not in allowed:
            f[i] = 0
    return f


# ── Strategy 1: Trend Following v2 (4H) — triple EMA alignment ──────

def strat_trend_following(close, high, low, volume, params):
    n = len(close)
    pos = np.zeros(n)
    ef = _ema(close, params["ema_fast"])
    em = _ema(close, params["ema_mid"])
    es = _ema(close, params.get("ema_slow", 50))
    adx_v = _adx(high, low, close, 14)
    mh = _macd_hist(close)
    av = _atr(high, low, close, 14)

    direction = 0
    trail = 0.0
    for i in range(1, n):
        if np.isnan(ef[i]) or np.isnan(em[i]) or np.isnan(es[i]) or np.isnan(adx_v[i]) or np.isnan(mh[i]) or np.isnan(av[i]):
            continue
        bull_x = ef[i] > em[i] and ef[i-1] <= em[i-1]
        bear_x = ef[i] < em[i] and ef[i-1] >= em[i-1]
        bull_align = ef[i] > em[i] > es[i]
        bear_align = ef[i] < em[i] < es[i]

        if direction == 0:
            if bull_x and bull_align and adx_v[i] > params["adx_thresh"] and mh[i] > 0:
                direction = 1
                trail = close[i] - av[i] * params["atr_trail"]
                pos[i] = 1
            elif bear_x and bear_align and adx_v[i] > params["adx_thresh"] and mh[i] < 0:
                direction = -1
                trail = close[i] + av[i] * params["atr_trail"]
                pos[i] = -1
        elif direction == 1:
            trail = max(trail, close[i] - av[i] * params["atr_trail"])
            if close[i] < trail or bear_x:
                direction = 0
            else:
                pos[i] = 1
        else:
            trail = min(trail, close[i] + av[i] * params["atr_trail"])
            if close[i] > trail or bull_x:
                direction = 0
            else:
                pos[i] = -1
    return pos

TREND_GRID = [
    {"ema_fast": f, "ema_mid": m, "ema_slow": s, "adx_thresh": a, "atr_trail": t}
    for f in (8, 10, 12, 14)
    for m in (25, 30, 40)
    for s in (45, 50, 60)
    for a in (18, 22, 26)
    for t in (2.0, 2.5, 3.0, 3.5, 4.0)
    if f < m < s
]


# ── Strategy 2: Mean Reversion (2H) — internal ADX filter ────────────

def strat_mean_reversion(close, high, low, volume, params):
    n = len(close)
    pos = np.zeros(n)
    bm, bu, bl = _bb(close, params["bb_len"], params["bb_std"])
    rv = _rsi(close, 14)
    av = _atr(high, low, close, 14)
    vm = _sma(volume, 20)
    adx_v = _adx(high, low, close, 14)

    vol_mult = params.get("vol_mult", 1.2)
    sl_mult = params.get("sl_mult", 1.5)
    max_hold = params.get("max_hold", 20)
    adx_max = params.get("adx_max", 25)
    direction = 0
    sl_level = 0.0
    bars_held = 0

    for i in range(1, n):
        if np.isnan(bl[i]) or np.isnan(rv[i]) or np.isnan(vm[i]) or np.isnan(av[i]) or np.isnan(adx_v[i]):
            continue
        vol_ok = vm[i] > 0 and volume[i] > vm[i] * vol_mult
        adx_ok = adx_v[i] < adx_max

        if direction == 0:
            if close[i] <= bl[i] and rv[i] < params["rsi_os"] and vol_ok and adx_ok:
                direction = 1
                sl_level = close[i] - av[i] * sl_mult
                pos[i] = 1
                bars_held = 0
            elif close[i] >= bu[i] and rv[i] > params["rsi_ob"] and vol_ok and adx_ok:
                direction = -1
                sl_level = close[i] + av[i] * sl_mult
                pos[i] = -1
                bars_held = 0
        elif direction == 1:
            bars_held += 1
            if close[i] < sl_level or close[i] >= bm[i] or bars_held >= max_hold:
                direction = 0
            else:
                pos[i] = 1
        else:
            bars_held += 1
            if close[i] > sl_level or close[i] <= bm[i] or bars_held >= max_hold:
                direction = 0
            else:
                pos[i] = -1
    return pos

MR_GRID = [
    {"bb_len": b, "bb_std": s, "rsi_os": o, "rsi_ob": ob,
     "vol_mult": vm, "sl_mult": sl, "max_hold": mh, "adx_max": am}
    for b in (20, 25, 30)
    for s in (1.8, 2.0, 2.2)
    for o in (28, 32, 36)
    for ob in (66, 70, 74)
    for vm in (0.8, 1.0, 1.3)
    for sl in (1.5, 2.0)
    for mh in (10, 16, 24)
    for am in (18, 22, 28)
]


# ── Strategy 3: Swing Momentum (4H) — replaces Breakout ──────────────

def strat_swing_momentum(close, high, low, volume, params):
    """RSI 50-line crossover + EMA trend filter + volume + ATR trail."""
    n = len(close)
    pos = np.zeros(n)
    rv = _rsi(close, params["rsi_len"])
    av = _atr(high, low, close, 14)
    vm = _sma(volume, 20)
    et = _ema(close, params["ema_len"])

    direction = 0
    trail = 0.0
    for i in range(1, n):
        if np.isnan(rv[i]) or np.isnan(av[i]) or np.isnan(vm[i]) or np.isnan(et[i]):
            continue
        vol_ok = vm[i] > 0 and volume[i] > vm[i] * params["vol_thresh"]
        bull_rsi = rv[i] > params.get("rsi_bull", 50) and rv[i-1] <= params.get("rsi_bull", 50)
        bear_rsi = rv[i] < params.get("rsi_bear", 50) and rv[i-1] >= params.get("rsi_bear", 50)
        above = close[i] > et[i]
        below = close[i] < et[i]

        if direction == 0:
            if bull_rsi and vol_ok and above:
                direction = 1
                trail = close[i] - av[i] * params["atr_trail"]
                pos[i] = 1
            elif bear_rsi and vol_ok and below:
                direction = -1
                trail = close[i] + av[i] * params["atr_trail"]
                pos[i] = -1
        elif direction == 1:
            trail = max(trail, close[i] - av[i] * params["atr_trail"])
            if close[i] < trail or bear_rsi:
                direction = 0
            else:
                pos[i] = 1
        else:
            trail = min(trail, close[i] + av[i] * params["atr_trail"])
            if close[i] > trail or bull_rsi:
                direction = 0
            else:
                pos[i] = -1
    return pos

SWING_GRID = [
    {"rsi_len": r, "ema_len": e, "vol_thresh": v, "atr_trail": t,
     "rsi_bull": rb, "rsi_bear": rr}
    for r in (16, 18, 20, 22)
    for e in (40, 50, 60)
    for v in (0.8, 1.0, 1.2)
    for t in (2.0, 2.5, 3.0, 3.5)
    for rb in (48, 50, 52)
    for rr in (50, 52, 54)
]


# ── Strategy 4: Trend Pullback (1H) — fine-tuned grid ────────────────

def strat_pullback(close, high, low, volume, params):
    n = len(close)
    pos = np.zeros(n)
    ema_s = _ema(close, params["ema_slow"])
    ema_f = _ema(close, params["ema_fast"])
    rv = _rsi(close, 14)
    av = _atr(high, low, close, 14)
    vm = _sma(volume, 20)
    adx_v = _adx(high, low, close, 14)

    trend_lb = params.get("trend_lb", 12)
    cooldown = params.get("cooldown", 12)
    max_hold = params.get("max_hold", 48)
    min_slope = params.get("min_slope", 0.05)
    adx_min = params.get("adx_min", 18)
    direction = 0
    trail = 0.0
    bars_exit = cooldown
    bars_held = 0

    for i in range(trend_lb + 1, n):
        if np.isnan(ema_s[i]) or np.isnan(ema_f[i]) or np.isnan(rv[i]) or np.isnan(av[i]) or np.isnan(vm[i]) or np.isnan(adx_v[i]):
            continue
        slope_pct = (ema_s[i] - ema_s[i - trend_lb]) / ema_s[i - trend_lb] * 100
        t_up = slope_pct > min_slope and adx_v[i] > adx_min
        t_dn = slope_pct < -min_slope and adx_v[i] > adx_min
        vol_ok = vm[i] > 0 and volume[i] > vm[i] * params["vol_thresh"]
        rsi_low = any(rv[max(0, i-k)] < 40 for k in range(1, 5) if not np.isnan(rv[max(0, i-k)]))
        rsi_high = any(rv[max(0, i-k)] > 60 for k in range(1, 5) if not np.isnan(rv[max(0, i-k)]))
        pb_up = close[i] > ema_f[i] and close[i-1] <= ema_f[i-1]
        pb_dn = close[i] < ema_f[i] and close[i-1] >= ema_f[i-1]

        if direction == 0:
            bars_exit += 1
            if bars_exit < cooldown:
                continue
            if t_up and pb_up and rsi_low and rv[i] > 40 and vol_ok:
                direction = 1
                trail = close[i] - av[i] * params["atr_trail"]
                pos[i] = 1; bars_held = 0
            elif t_dn and pb_dn and rsi_high and rv[i] < 60 and vol_ok:
                direction = -1
                trail = close[i] + av[i] * params["atr_trail"]
                pos[i] = -1; bars_held = 0
        elif direction == 1:
            bars_held += 1
            trail = max(trail, close[i] - av[i] * params["atr_trail"])
            if close[i] <= trail or bars_held >= max_hold:
                direction = 0; bars_exit = 0
            else:
                pos[i] = 1
        else:
            bars_held += 1
            trail = min(trail, close[i] + av[i] * params["atr_trail"])
            if close[i] >= trail or bars_held >= max_hold:
                direction = 0; bars_exit = 0
            else:
                pos[i] = -1
    return pos

PULLBACK_GRID = [
    {"ema_slow": es, "ema_fast": ef, "vol_thresh": v, "atr_trail": t,
     "cooldown": cd, "max_hold": mh, "trend_lb": 12,
     "min_slope": ms, "adx_min": am}
    for es in (40, 50)
    for ef in (6, 8, 10)
    for v in (0.8, 1.0)
    for t in (0.8, 1.0, 1.5)
    for cd in (12, 24)
    for mh in (30, 48)
    for ms in (0.05, 0.15, 0.3, 0.5)
    for am in (15, 20, 25)
    if ef < es
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


def optimize(close, high, low, volume, fn, grid, af, regimes=None, allowed=None):
    best_sh = -np.inf
    best_p = grid[0]
    total = len(grid)
    check = max(1, total // 20)
    for idx, p in enumerate(grid):
        if idx % check == 0:
            print(f"    {idx}/{total} ({idx*100//total}%) best={best_sh:.3f}", end="\r", flush=True)
        pos = fn(close, high, low, volume, p)
        if regimes is not None and allowed is not None:
            pos = _regime_mask(pos, regimes, allowed)
        ret = compute_returns(pos, close)
        s = np.std(ret)
        sh = np.mean(ret) / s * np.sqrt(af) if s > 1e-10 else 0
        if sh > best_sh:
            best_sh = sh; best_p = p
    print(f"    {total}/{total} (100%) best={best_sh:.3f}                    ")
    return dict(best_p), round(float(best_sh), 3)


def analyze(name, tf, fn, grid, df, regimes=None, allowed=None):
    af = PERIODS_PER_YEAR.get(tf, 365)
    c = df["Close"].values.astype(float)
    h = df["High"].values.astype(float)
    l = df["Low"].values.astype(float)
    v = df["Volume"].values.astype(float)
    dates = df.index

    rfilt = f"regime={allowed}" if allowed else "no filter"
    print(f"\n{'='*72}")
    print(f"  {name} ({tf}) | {len(df)} bars | {dates[0].date()} -> {dates[-1].date()} | {rfilt}")
    print(f"{'='*72}")

    if allowed and regimes is not None:
        ab = sum(1 for r in regimes if r in allowed)
        print(f"  Active: {ab}/{len(regimes)} ({ab*100//len(regimes)}%)")

    print(f"  Optimizing ({len(grid)} combos)...")
    bp, _ = optimize(c, h, l, v, fn, grid, af, regimes, allowed)
    print(f"  Params: {bp}")

    pos = fn(c, h, l, v, bp)
    if regimes is not None and allowed is not None:
        pos = _regime_mask(pos, regimes, allowed)
    ret = compute_returns(pos, c)
    trades = extract_trades(pos, c, dates)
    fm = compute_metrics(ret, af)

    print(f"\n  Full: Ret={fm['ret']:>7.1f}%  Sharpe={fm['sharpe']:>6.3f}  MDD={fm['mdd']:>6.1f}%  Trades={len(trades)}")
    if trades:
        w = [t for t in trades if t["pnl"] > 0]
        lo = [t for t in trades if t["pnl"] <= 0]
        wr = len(w) / len(trades) * 100
        aw = np.mean([t["pnl"] for t in w]) if w else 0
        al = np.mean([t["pnl"] for t in lo]) if lo else 0
        ls = sum(1 for t in trades if t["dir"] == "L")
        ss = sum(1 for t in trades if t["dir"] == "S")
        ab = np.mean([t["bars"] for t in trades])
        print(f"  WR={wr:.1f}% AvgW={aw:.2f}% AvgL={al:.2f}% L/S={ls}/{ss} Hold={ab:.1f}bars")

    years = sorted(set(d.year for d in dates))
    yr_results = {}
    print(f"  Years:")
    for yr in years:
        mask = np.array([d.year == yr for d in dates])
        if mask.sum() < 50: continue
        ym = compute_metrics(ret[mask], af)
        yt = [t for t in trades if t.get("entry_date", "").startswith(str(yr))]
        yr_results[yr] = ym
        print(f"    {yr}: Ret={ym['ret']:>7.1f}%  Sharpe={ym['sharpe']:>6.3f}  MDD={ym['mdd']:>6.1f}%  T={len(yt)}")

    six_ago = dates[-1] - pd.Timedelta(days=182)
    oos_mask = np.array([d >= six_ago for d in dates])
    om = {"sharpe": 0}
    if oos_mask.sum() > 50:
        om = compute_metrics(ret[oos_mask], af)
        ot = [t for t in trades if t.get("entry_date", "") >= str(six_ago)[:10]]
        print(f"  OOS(6m): Ret={om['ret']:>7.1f}%  Sharpe={om['sharpe']:>6.3f}  MDD={om['mdd']:>6.1f}%  T={len(ot)}")

    issues = []
    if fm["sharpe"] < 1.2: issues.append(f"Full Sharpe {fm['sharpe']:.3f} < 1.2")
    for yr, ym in yr_results.items():
        if ym["sharpe"] < 0.8: issues.append(f"{yr} Sharpe {ym['sharpe']:.3f} < 0.8")
    if len(trades) < 15: issues.append(f"Only {len(trades)} trades")
    if fm["mdd"] < -40: issues.append(f"MDD {fm['mdd']:.1f}%")

    tag = "PASS" if not issues else "FAIL"
    print(f"  [{tag}]", "; ".join(issues) if issues else "All criteria met!")
    return {"name": name, "tf": tf, "params": bp, "fm": fm, "yr": yr_results,
            "om": om, "trades": trades, "issues": issues}


def main():
    print("=" * 72)
    print("  Elite BTC/USDC Backtester — Iteration 3")
    print(f"  {START_DATE} -> {END_DATE} | Fees {FEE_PCT}%+{SLIP_PCT}%")
    print("=" * 72)

    print("\nLoading data...")
    d4 = fetch_ohlcv(SYMBOL, "4h", START_DATE, END_DATE)
    d2 = fetch_ohlcv(SYMBOL, "2h", START_DATE, END_DATE)
    d1 = fetch_ohlcv(SYMBOL, "1h", START_DATE, END_DATE)
    print(f"4H={len(d4)}, 2H={len(d2)}, 1H={len(d1)}")

    def ex(df):
        return (df["High"].values.astype(float), df["Low"].values.astype(float),
                df["Close"].values.astype(float), df["Volume"].values.astype(float))

    print("\nRegimes...")
    r4 = classify_regimes(*ex(d4))
    r1 = classify_regimes(*ex(d1))
    for lbl, r in [("4H", r4), ("1H", r1)]:
        u, c = np.unique(r, return_counts=True)
        print(f"  {lbl}: " + ", ".join(f"{rr}={cc}({cc*100//len(r)}%)" for rr, cc in zip(u, c)))

    results = []

    results.append(analyze("Trend Following", "4h", strat_trend_following, TREND_GRID, d4,
                           regimes=r4, allowed={"uptrend", "downtrend"}))

    results.append(analyze("Mean Reversion", "2h", strat_mean_reversion, MR_GRID, d2))

    results.append(analyze("Swing Momentum", "4h", strat_swing_momentum, SWING_GRID, d4,
                           regimes=r4, allowed={"uptrend", "downtrend"}))

    # Pullback: no external regime filter — internal ADX + slope filters provide quality control
    results.append(analyze("Trend Pullback", "1h", strat_pullback, PULLBACK_GRID, d1))

    print(f"\n{'='*72}")
    print(f"  SUMMARY — Iteration 3")
    print(f"{'='*72}")
    ok = True
    for r in results:
        m = r["fm"]
        tag = "PASS" if not r["issues"] else "FAIL"
        if r["issues"]: ok = False
        print(f"  {r['name']:>20s} ({r['tf']}): Sharpe={m['sharpe']:>6.3f}  "
              f"Ret={m['ret']:>7.1f}%  MDD={m['mdd']:>6.1f}%  T={len(r['trades']):>3d}  [{tag}]")
    print(f"\n  {'ALL PASS' if ok else 'NEEDS WORK'}")
    return results

if __name__ == "__main__":
    results = main()
