# Trading Agents Team

An autonomous multi-agent trading system that connects TradingView Pine Script strategies to Binance Spot, using a team of four specialized AI agents to continuously evaluate BTC/USDT and hot-swap strategies without manual input.

## The Problem

Traditional bots (Pionex, 3Commas, etc.) run a single static strategy. When the market shifts from ranging to trending, the bot keeps trading the wrong regime until a human notices and manually reconfigures it. This team eliminates that gap.

## How It Works

The system runs two independent pipelines, each orchestrated as a LangGraph state graph.

### Pipeline 1 — Analysis Loop (Scheduled)

Runs every 5 minutes via APScheduler.

```
Analyst --> Strategist --> END
```

1. **The Analyst** pulls 4H and 1H BTC/USDT candles from Binance, computes technical indicators (ADX, ATR, Bollinger Bands, EMAs, RSI, MACD, volume ratios), and asks the configured LLM to classify the current market regime as one of:
   - `trending_up` — strong uptrend, ADX > 25, EMA alignment bullish
   - `trending_down` — strong downtrend, ADX > 25, EMA alignment bearish
   - `ranging` — low ADX, narrow Bollinger Bands, sideways price action
   - `high_volatility` — ATR spike, wide Bollinger Bands, unstable direction
   - `breakout` — price breaking out of consolidation with rising ADX and volume surge
   - `accumulation` — tight consolidation with very narrow Bollinger Bands and building volume, pre-breakout phase

2. **The Strategist** maps the regime to the best-fit Pine Script strategy:
   - Trending regimes --> `trend_following`
   - Ranging --> `mean_reversion`
   - High volatility --> `scalping`
   - Breakout --> `trend_following` (ride the momentum after the break)
   - Accumulation --> `mean_reversion` (profit from the tight range while awaiting breakout)

   For edge cases (low confidence, regime transitions), the LLM provides a second opinion before committing. The active strategy is stored in MongoDB.

### Pipeline 2 — Execution Flow (Event-Driven)

Triggered automatically by a TradingView webhook — **not meant to be run manually or scheduled**.

```
Risk Manager --> Executor --> END
```

The execution pipeline is a **one-shot** process that handles a single trade signal and exits. The listening happens at the platform level, not inside the agent team:

1. The platform's webhook endpoint (`POST /api/webhook/tradingview`) is always listening as long as the server is running.
2. When TradingView fires a webhook, the platform validates the secret, checks the kill switch, deduplicates the signal, and matches the signal's `strategy_name` against the currently active strategy. Mismatched signals are logged but ignored.
3. If the signal matches, the platform **spawns** the execution pipeline as a subprocess for that specific signal.
4. **The Risk Manager** fetches the Binance account balance, calculates ATR-based position sizing at 2% risk per trade, checks drawdown limits (10% max), verifies open position caps (3 max), and either approves or rejects the trade.
5. **The Executor** places a market order on Binance Spot, polls for confirmation, records the fill in MongoDB, and sets an OCO stop-loss / take-profit order.
6. The pipeline exits. The next webhook will spawn a new execution pipeline.

> **Note:** Running execution mode manually from the UI will exit immediately because no signal data is provided. This is expected — execution is designed to be triggered by webhooks, not by the Run Now button.

## Signal Flow Architecture

The system uses a **passive filtering** design. No agent communicates with TradingView — the platform only listens.

```
TradingView (cloud)
  ├── trend_following.pine  ──┐
  ├── mean_reversion.pine   ──┼── All 3 strategies fire webhooks simultaneously
  └── scalping.pine         ──┘
                               │
                    POST /api/webhook/tradingview
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Platform Webhook   │
                    │  Filter:            │
                    │  signal.strategy == │──── NO ──→ Log & ignore
                    │  active_strategy?   │
                    └────────┬────────────┘
                             │ YES
                             ▼
                    Pipeline 2 (Execution)
                    Risk Manager → Executor → Binance
```

All three Pine Script strategies run independently on TradingView and fire signals whenever their entry conditions are met. The platform receives every signal but only acts on the one whose `strategy_name` matches the active strategy selected by Pipeline 1. The rest are logged and discarded.

The "hot-swapping" happens entirely on the platform side — Pipeline 1 writes the active strategy to MongoDB, and the webhook filter reads it. Nothing is changed on TradingView.

## Market Analysis Data Pipeline

Pipeline 1 analyzes the market by pulling real data directly from the **Binance API** (not TradingView) and running it through three stages:

### Stage 1 — Fetch raw candlestick data

The `fetch_data` node calls `get_klines()` on the Binance REST API:
- **100 candles on the 4-hour timeframe** — the primary analysis frame
- **100 candles on the 1-hour timeframe** — for finer resolution

Each candle contains open, high, low, close, and volume (OHLCV) for BTC/USDT.

### Stage 2 — Compute technical indicators

The `compute_indicators` node runs the 4H candles through the Python `ta` library and computes **19 indicators**:

| Category | Indicators |
|----------|-----------|
| Trend strength | ADX (Average Directional Index) |
| Volatility | ATR, ATR %, Bollinger Band width, BB upper / lower / middle |
| Trend direction | EMA(9), EMA(21), EMA(50), plus the slope of each over the last 3 periods |
| Momentum | RSI, MACD line, MACD signal, MACD histogram |
| Volume | Volume ratio (current volume vs. 20-period moving average) |
| Price | Current price |

### Stage 3 — LLM classifies the regime

All 19 indicators are formatted into a structured prompt and sent to the configured LLM (Google Gemini, Anthropic Claude, or DeepSeek — selectable from the Trading tab settings). The LLM reads the numbers and returns:
- **Regime** — one of `trending_up`, `trending_down`, `ranging`, `high_volatility`, `breakout`, `accumulation`
- **Confidence** — 0–100%
- **Reasoning** — a natural-language explanation of the classification

The result is stored in MongoDB's `market_regimes` collection and used by the Strategist to select the active strategy.

## Agent Summary

| Agent | Role | Key Inputs | Key Outputs |
|-------|------|-----------|-------------|
| Analyst | Market regime detection | Binance OHLCV candles | Regime classification + confidence |
| Strategist | Strategy selection | Regime + indicators | Active strategy stored in MongoDB |
| Risk Manager | Position sizing + risk gates | Account balance, ATR, signal | Approved/rejected + position size, SL, TP |
| Executor | Order placement | Signal + risk params | Binance order ID, fill price, trade record |

## Directory Structure

```
trading_agents/
├── shared/                    Shared code across all agents
│   ├── llm.py                 Multi-provider LLM wrapper (Gemini, Claude, DeepSeek)
│   ├── binance_client.py      Binance Spot API wrapper
│   ├── indicators.py          Technical indicator calculations (ta library)
│   ├── models.py              Data models (MarketRegime, TradeSignal, RiskParams, etc.)
│   ├── config.py              Trading pair, risk limits, indicator periods, LLM providers
│   ├── mongo.py               MongoDB helpers + trading config loaders
│   ├── logger.py              Logging config
│   └── utils.py               AGENT_ARGS loader
├── agent_analyst/             Market regime classification
│   ├── agent.py               LangGraph: fetch_data -> compute_indicators -> classify_regime
│   ├── nodes/
│   │   ├── fetch_data.py      Pulls OHLCV from Binance API
│   │   ├── compute_indicators.py  ADX, ATR, BB, EMA, RSI, MACD, volume
│   │   └── classify_regime.py Gemini-assisted regime classification
│   ├── tools/market_tools.py  @tool functions for market data
│   └── prompts/               Regime classification prompt templates
├── agent_strategist/          Strategy selection
│   ├── agent.py               LangGraph: evaluate -> select -> update_selection
│   ├── nodes/
│   │   ├── evaluate_strategies.py  Regime-to-strategy mapping
│   │   ├── select_strategy.py     Gemini for edge cases
│   │   └── update_selection.py    Writes to MongoDB
│   └── prompts/               Strategy selection prompt templates
├── agent_risk_manager/        Position sizing and risk gates
│   ├── agent.py               LangGraph: fetch_account -> calculate_risk -> approve_trade
│   └── nodes/
│       ├── fetch_account.py   Binance balance + open orders
│       ├── calculate_risk.py  ATR-based sizing, SL/TP levels
│       └── approve_trade.py   Drawdown check, position limits, final gate
├── agent_executor/            Order execution
│   ├── agent.py               LangGraph: validate -> place_order -> confirm -> set_stop_loss
│   ├── nodes/
│   │   ├── validate_signal.py Signal format + strategy match check
│   │   ├── place_order.py     Binance market order (or dry-run log)
│   │   ├── confirm_order.py   Poll fill, record trade in MongoDB
│   │   └── set_stop_loss.py   OCO stop-loss + take-profit order
│   └── tools/binance_tools.py @tool functions for Binance orders
├── orchestrator/
│   ├── main.py                Entry point — reads mode from AGENT_ARGS
│   ├── graph.py               Builds analysis or execution graph
│   └── state.py               AnalysisPipelineState / ExecutionPipelineState
├── ui/                        Custom tabs plugin (loaded on the agent detail page)
│   ├── tabs.json              Tab definitions (Trading, Trades, Signals, Strategy)
│   └── tabs/
│       ├── trading.html       Dashboard (regime, risk, stats) + Settings (LLM, risk, indicators)
│       ├── trades.html        Recent executed trades table
│       ├── signals.html       Recent trade signals table
│       └── strategy.html      Strategy selection history
├── strategies/                TradingView Pine Script strategies
│   ├── trend_following.pine   EMA crossover + ADX + MACD
│   ├── mean_reversion.pine    Bollinger Band bounce + RSI + volume
│   └── scalping.pine          VWAP + EMA(9) + volume spike
├── tests/
│   └── test_pipeline.py       State schema and mapping tests
├── requirements.txt           Python dependencies
└── run_config.json            Platform run form (mode + dry_run selector)
```

## Configuration

Settings can be configured in two ways:

1. **Trading tab Settings panel** (recommended) — expand the Settings section at the bottom of the Trading tab to select the LLM provider/model, enter API keys, and adjust risk and indicator parameters. Click **Save Settings** to persist everything to MongoDB. These settings survive server restarts.
2. **Environment variables** — set in `.env` as fallback defaults. MongoDB settings take precedence when present.

> **Important:** The **Indicator Periods** in the Settings panel (ADX Period, ATR Period, BB Period, EMA Fast/Mid/Slow, RSI Period, Volume MA Period) are used **only by Pipeline 1's Analyst** for computing the 19 technical indicators that feed into LLM-based regime classification. They have **no effect** on the Pine Script strategies running on TradingView. Each Pine Script strategy has its own independent parameters — see [Pine Script Strategies](#pine-script-strategies) below for details.

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | LLM provider (`gemini`, `claude`, or `deepseek`) | `gemini` |
| `LLM_MODEL` | Model ID for the selected provider | `gemini-2.5-flash` |
| `GEMINI_API_KEY` | Google Gemini API key | (required if using Gemini) |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key | (required if using Claude) |
| `DEEPSEEK_API_KEY` | DeepSeek API key | (required if using DeepSeek) |
| `BINANCE_API_KEY` | Binance Spot API key | (required) |
| `BINANCE_API_SECRET` | Binance Spot API secret | (required) |
| `TRADING_PAIR` | Symbol to trade | `BTCUSDT` |
| `MAX_RISK_PER_TRADE` | Fraction of portfolio risked per trade | `0.02` (2%) |
| `MAX_OPEN_POSITIONS` | Maximum concurrent positions | `3` |
| `MAX_DRAWDOWN` | Pause trading above this drawdown | `0.10` (10%) |

### Supported LLM Providers

| Provider | Models | Notes |
|----------|--------|-------|
| Google Gemini | `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.0-flash` | Free tier available |
| Anthropic Claude | `claude-sonnet-4-20250514`, `claude-3-5-haiku-20241022` | Paid API |
| DeepSeek | `deepseek-chat`, `deepseek-reasoner` | Paid API (very low cost) |

## Running

### Via the Platform UI

1. Upload this team as a ZIP via the Dashboard (with tag `trading`).
2. Once the venv builds, go to the agent detail page.
3. The custom tabs (**Trading**, **Trades**, **Signals**, **Strategy**) will appear automatically.
4. Click **Run Now** (top right) to open the run modal — select **Pipeline Mode** (`analysis` or `execution`) and **Dry Run**, then click **Run**.
5. Alternatively, use the **Run Analysis** button on the **Trading** tab to quickly trigger an analysis run.
6. Or set up a 5-minute interval schedule for continuous analysis.

### Manual Analysis Run

The platform scheduler triggers this automatically, but you can also run it on demand from the **Trading** tab on the agent detail page (click "Run Analysis") or via the API:

```
POST /api/agents/{agent_id}/run
{"mode": "analysis"}
```

### Webhook-Triggered Execution

When TradingView fires a webhook to `POST /api/webhook/tradingview`, the platform automatically triggers the execution pipeline if the signal matches the active strategy. No manual action needed.

## Safety

- **Dry-run mode** is enabled by default. Set `TRADING_DRY_RUN=false` in `.env` to execute real trades.
- **Kill switch** on the Trading tab instantly disables all trading. State is persisted to MongoDB when Save Settings is clicked.
- **Duplicate detection** ignores identical signals within a 60-second window.
- **Daily trade cap** prevents runaway execution (default: 50 trades/day).
- **Drawdown limit** pauses trading if portfolio drops more than 10% from peak.
- **Max positions** prevents over-exposure (default: 3 concurrent).

## Pine Script Strategies

Three TradingView strategies in `strategies/` send webhook alerts to this system. Each strategy has its **own parameters defined as TradingView inputs** inside the `.pine` file — these are completely independent from the Indicator Periods in the Settings panel (which only affect the Analyst's regime classification). To change a strategy's trading behavior, edit the `.pine` file directly or override the inputs in TradingView's strategy settings.

| Strategy | Regime | Timeframe | Entry Logic |
|----------|--------|-----------|-------------|
| `trend_following` | Trending | 4H | EMA(9/21) crossover + ADX > 25 + MACD confirmation |
| `mean_reversion` | Ranging | 4H | Bollinger Band bounce + RSI oversold/overbought + volume |
| `scalping` | High volatility | 1H | VWAP + EMA(9) + volume spike, wide TP (3× ATR) |

### Strategy Parameters

#### `trend_following.pine`

| Parameter | Default | Description |
|-----------|---------|-------------|
| EMA Fast Length | 9 | Fast EMA for crossover signal |
| EMA Mid Length | 21 | Mid EMA for crossover signal |
| ADX Length | 14 | ADX period for trend strength |
| ADX Threshold | 25.0 | Minimum ADX to confirm a strong trend |
| ATR Length | 14 | ATR period for trailing stop |
| ATR Trailing Stop Multiplier | 2.0 | Trailing stop distance as multiple of ATR |

#### `mean_reversion.pine`

| Parameter | Default | Description |
|-----------|---------|-------------|
| Bollinger Band Length | 20 | BB lookback period |
| Bollinger Band Std Dev | 2.0 | BB width in standard deviations |
| RSI Length | 14 | RSI lookback period |
| RSI Oversold Level | 30.0 | RSI threshold for buy signal |
| RSI Overbought Level | 70.0 | RSI threshold for sell signal |
| Volume Confirmation Multiple | 1.5 | Volume must exceed this × volume MA |
| ATR Length | 14 | ATR period for stop-loss |
| ATR Stop Loss Multiple | 1.5 | Stop-loss distance as multiple of ATR |

#### `scalping.pine`

| Parameter | Default | Description |
|-----------|---------|-------------|
| EMA Length | 10 | EMA period for trend filter |
| ATR Length | 22 | ATR period for SL/TP calculation |
| ATR Stop Loss Multiple | 0.65 | Stop-loss distance as multiple of ATR |
| ATR Take Profit Multiple | 3.0 | Take-profit distance as multiple of ATR |
| Volume Spike Threshold | 2.75× | Volume must exceed this × volume MA |
| Volume MA Length | 35 | Lookback for volume moving average |
| Session Start Hour (UTC) | 8 | Start of active trading window |
| Session End Hour (UTC) | 19 | End of active trading window |
| RSI Length | 10 | RSI period for momentum confirmation |
| RSI Minimum for Entry | 50 | Only enter when RSI is above this level |
| Cooldown Bars After Exit | 6 | Minimum bars to wait between trades |

Each strategy sends a JSON webhook payload containing `strategy_name`, `action`, `ticker`, `price`, and a shared `secret` for authentication.

## Strategy Backtest — Walk-Forward Analysis Engine

The platform includes a walk-forward backtesting engine (`agent_platform/api/routes/backtest.py`) that translates the three Pine Script strategies above into Python and runs them against historical Binance data. The purpose is to expose curve-fitting: comparing what a retail backtest shows (in-sample, optimised on all data) vs. what actually happens on unseen data (out-of-sample, blind-tested).

### How Walk-Forward Analysis Works

Traditional backtesting optimises a strategy over the entire historical dataset and reports the result — this is the "illusion." Walk-forward analysis splits the data into rolling windows and reveals the "reality":

```
 ┌─── Train (optimise) ───┐┌─ Blind Test ─┐
 │  Find best params here  ││ Apply blindly │
 └─────────────────────────┘└──────────────┘
          ─────── slide forward ───────►
 ┌─── Train (optimise) ───┐┌─ Blind Test ─┐
 └─────────────────────────┘└──────────────┘
          ─────── slide forward ───────►
 ┌─── Train (optimise) ───┐┌─ Blind Test ─┐
 └─────────────────────────┘└──────────────┘
```

1. **Train window** — the optimiser grid-searches all parameter combinations and picks the set with the highest Sharpe ratio.
2. **Blind test window** — the winning parameters are applied to data the optimiser has never seen. Only these out-of-sample returns are kept.
3. **Slide forward** — the window advances by the test length and repeats.
4. **Stitch** — all blind-test returns are concatenated into a single equity curve. This is the realistic performance estimate.

The engine then compares this stitched out-of-sample result against a conventional backtest (global optimisation on all data) to quantify the degradation.

### Strategies (Python Translations)

Each Pine Script strategy is translated to Python with the same core logic. The timeframe and optimised parameters differ per strategy:

| Strategy | Timeframe | Indicators | Entry | Exit | Optimised Parameters |
|----------|-----------|------------|-------|------|---------------------|
| `scalping` | **15m** | EMA, VWAP, RSI, Volume MA, ATR | Price > VWAP, Price > EMA, volume spike, RSI > 50 | Price < VWAP or < EMA, or SL/TP hit | `ema_len`, `vol_thresh`, `atr_sl`, `atr_tp` (144 combos) |
| `trend_following` | **4h** | Dual EMA, ADX, MACD, ATR | Bullish EMA cross + ADX above threshold + MACD > 0 | Bearish cross, weak trend, or trailing stop | `ema_fast`, `ema_mid`, `adx_thresh`, `atr_trail` (~100 combos) |
| `mean_reversion` | **4h** | Bollinger Bands, RSI, Volume MA, ATR | Price at lower BB + RSI oversold + volume confirmation | Upper BB + RSI overbought, mean reversion to middle BB, or SL | `bb_len`, `bb_std`, `rsi_os`, `rsi_ob` (81 combos) |

Some Pine Script inputs (time filter, cooldown bars, webhook secret) are not translated because they don't apply to historical backtesting.

### Technical Indicators

All indicators are implemented in pure numpy/pandas to avoid external TA library dependencies:

| Function | Description |
|----------|-------------|
| `_ema` | Exponential Moving Average via `pandas.ewm` |
| `_sma` | Simple Moving Average via rolling window |
| `_rsi` | Relative Strength Index (rolling mean of gains vs. losses) |
| `_atr` | Average True Range (max of high−low, |high−prev_close|, |low−prev_close|) |
| `_bb` | Bollinger Bands (middle ± n × rolling std) |
| `_adx` | Average Directional Index (+DI, −DI, DX, smoothed ADX) |
| `_macd` | MACD histogram (fast EMA − slow EMA − signal EMA) |
| `_vwap` | Rolling Volume-Weighted Average Price over a lookback period |

### Optimisation

Each fold performs a grid search over the strategy's parameter space:

- Iterates every parameter combination in the grid
- Executes the strategy, computes per-candle returns with transaction costs (exchange fee + slippage deducted on every position change)
- Calculates the annualised Sharpe ratio (annualisation factor depends on the timeframe: √35,040 for 15m, √2,190 for 4h)
- Selects the parameter set with the highest Sharpe

### OHLCV Data Caching (MongoDB Timeseries)

OHLCV data is cached in a MongoDB timeseries collection (`ohlcv`) so subsequent backtest runs skip the Binance download entirely:

```
agent_platform/db/ohlcv_cache.py
```

- **Collection type:** MongoDB timeseries with `timeField=timestamp`, `metaField=meta` (symbol + timeframe), granularity `minutes`
- **TTL:** 4 years (`expireAfterSeconds`). MongoDB automatically purges candles older than 4 years — no cron job or manual cleanup needed.
- **Smart download:** Before fetching from Binance, the cache layer checks the stored date range. If the requested range is fully covered, data is served from MongoDB. If there are gaps at the start or end, only the missing portion is downloaded and appended. This makes the first run slow (Binance API) and all subsequent runs near-instant (MongoDB read).

### API and Streaming

The engine exposes a single endpoint:

```
POST /api/backtest/run
```

Request body:

```json
{
  "ticker": "BTCUSDT",
  "start": "2024-01-01",
  "end": "2025-01-01",
  "train_days": 14,
  "test_days": 3,
  "strategy": "scalping",
  "exchange_fee": 0.10,
  "slippage": 0.05
}
```

Response: Server-Sent Events (SSE) stream via `StreamingResponse`. Each event is a JSON object with a `type` field:

| Event type | When | Key fields |
|------------|------|------------|
| `info` | After data loads | `total_folds`, `data_points`, `timeframe` |
| `fold` | After each fold completes | `fold_num`, `params`, `train_sharpe`, `oos_return`, `oos_trades` |
| `complete` | After all folds finish | `is_metrics`, `oos_metrics`, `degradation`, equity curves, fold details |
| `error` | On failure | `message` |

The frontend consumes this stream via `fetch` + `ReadableStream` and renders fold-by-fold progress in real time.

### Dashboard Sections

The Strategy Backtest page (`/strategy-backtest`) renders four sections after analysis completes:

1. **Walk-Forward Timeline** — horizontal bar chart showing each fold's train (blue) and blind test (orange) windows
2. **Parameter Shift Table** — shows how the "optimal" parameters change across folds, proving that no single fixed set works across all market regimes
3. **Illusion vs. Reality** — side-by-side metric cards (total return, Sharpe, max drawdown, trade count) for in-sample vs. out-of-sample, plus degradation figures
4. **Equity Curve** — overlaid line chart comparing the retail backtest equity (in-sample) against the walk-forward equity (out-of-sample), with shaded bands marking each blind test window
