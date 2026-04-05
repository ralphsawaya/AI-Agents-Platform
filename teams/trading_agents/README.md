# Trading Agents Team

An autonomous multi-agent trading system that connects TradingView Pine Script strategies to **Binance USDT-M Futures**, using a team of four specialized AI agents to continuously evaluate BTC/USDT and hot-swap strategies without manual input.

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
   - `uptrend` — sustained directional move upward, ADX > 22, triple EMA alignment bullish, positive EMA slope
   - `downtrend` — sustained directional move downward, ADX > 22, triple EMA alignment bearish, negative EMA slope
   - `ranging` — sideways/mean-reverting market, low directional bias, ADX < 22 or EMAs not aligned
   - `volatile_breakout` — high-volatility expansion from consolidation, ATR > 2.5%, wide BB, volume surge

2. **The Strategist** maps the regime to compatible strategies (multiple can be active):
   - Uptrend / Downtrend --> `ema_trend`, `rsi_momentum`, `macd_trend`
   - Ranging --> `rsi_momentum`
   - Volatile breakout --> `rsi_momentum`, `macd_trend`

   All three strategies have been walk-forward validated on 2+ years of BTC data with out-of-sample profitability. For edge cases (low confidence, regime transitions), the LLM provides a second opinion before committing. The active strategy is stored in MongoDB.

### Pipeline 2 — Execution Flow (Event-Driven)

Triggered automatically by a TradingView webhook — **not meant to be run manually or scheduled**.

```
Risk Manager --> Executor --> END
```

The execution pipeline is a **one-shot** process that handles a single trade signal and exits. The listening happens at the platform level, not inside the agent team:

1. The platform's webhook endpoint (`POST /api/webhook/tradingview`) is always listening as long as the server is running.
2. When TradingView fires a webhook, the platform validates the secret, checks the kill switch, deduplicates the signal, and matches the signal's `strategy_name` against the currently active strategy. For **entry signals** (open long or open short), only the active strategy is accepted. For **exit signals** (close / reduce), the platform also checks whether the signal's strategy has an open position — if so, the signal is allowed through even after a strategy switch, so the strategy that opened a position can close it.
3. If the signal matches (or is an exit passthrough), the platform **spawns** the execution pipeline as a subprocess for that specific signal.
4. **The Risk Manager** fetches the Binance USDT-M Futures account balance, fetches ATR on the **4H timeframe** (all strategies operate on 4H), calculates strategy-aware position sizing at 2% risk per trade, checks drawdown limits (10% max), verifies open position caps (3 max), and either approves or rejects the trade. Stop-loss distances are tailored per strategy (e.g. wider 3× ATR "disaster stop" for `ema_trend` and `macd_trend` since their Pine Script trailing stops handle normal exits; 2.5× ATR for `rsi_momentum`).
5. **The Executor** places a market order on **Binance USDT-M Futures**, polls for confirmation, records the fill in MongoDB, and sets protective orders (e.g. OCO stop-loss / take-profit) appropriate for futures.
6. The pipeline exits. The next webhook will spawn a new execution pipeline.

> **Note:** Running execution mode manually from the UI will exit immediately because no signal data is provided. This is expected — execution is designed to be triggered by webhooks, not by the Run Now button.

## Signal Flow Architecture

The system uses a **passive filtering** design. No agent communicates with TradingView — the platform only listens.

```
TradingView (cloud)
  ├── ema_trend.pine      ──┐
  ├── rsi_momentum.pine   ──┼── All three strategies fire webhooks simultaneously
  └── macd_trend.pine     ──┘
                               │
                    POST /api/webhook/tradingview
                               │
                               ▼
                    ┌──────────────────────────┐
                    │  Platform Webhook Filter  │
                    │                          │
                    │  Entry (long/short):     │
                    │  strategy == active?  ───│──── NO ──→ Log & ignore
                    │                          │
                    │  Exit / close:           │
                    │  strategy == active       │
                    │  OR has open position? ──│──── NO ──→ Log & ignore
                    └────────┬─────────────────┘
                             │ YES
                             ▼
                    Pipeline 2 (Execution)
                    Risk Manager → Executor → Binance USDT-M Futures
```

All three Pine Script strategies run independently on TradingView and fire signals whenever their entry conditions are met. The platform receives every signal and applies a two-tier filter:

- **Entry signals (open long or open short):** only accepted from the currently active strategy.
- **Exit signals (close / reduce):** accepted from the active strategy **or** from any strategy that has an open position. This ensures a strategy that opened a position can always close it, even after a strategy switch.

The "hot-swapping" happens entirely on the platform side — Pipeline 1 writes the active strategy to MongoDB, and the webhook filter reads it. Nothing is changed on TradingView. When the strategy switches, the Strategist agent also **cancels all open Binance USDT-M Futures orders** from the previous strategy to prevent interference.

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

### Stage 3 — Classify the regime (LLM + quantitative cross-check)

All 19 indicators are formatted into a structured prompt and sent to the configured LLM (Google Gemini, Anthropic Claude, DeepSeek, Groq, or OpenAI — selectable from the Settings tab). The LLM reads the numbers and returns:
- **Regime** — one of `uptrend`, `downtrend`, `ranging`, `volatile_breakout`
- **Confidence** — 0–100%
- **Reasoning** — a natural-language explanation of the classification

To guard against LLM inconsistency, the classifier runs a **deterministic quantitative fallback** in parallel using the same indicators (ADX thresholds, BB width percentile, ATR %, volume ratio, EMA alignment). The two results are cross-checked:
- If they **agree** → the LLM result is used (higher nuance).
- If they **disagree** and LLM confidence is **below 65%** → the quantitative result wins.
- If they **disagree** but LLM confidence is **high** → the LLM result is kept.

Both the LLM regime, quantitative regime, and final decision are stored in MongoDB's `market_regimes` collection for auditability.

## Agent Summary

| Agent | Role | Key Inputs | Key Outputs |
|-------|------|-----------|-------------|
| Analyst | Market regime detection (LLM + quantitative cross-check) | Binance OHLCV candles | Regime classification + confidence |
| Strategist | Strategy selection | Regime + indicators | Active strategy stored in MongoDB |
| Risk Manager | Timeframe-aware position sizing + risk gates | Account balance, ATR (fetched on strategy's native timeframe), signal + strategy name | Approved/rejected + position size, SL, TP |
| Executor | Order placement | Signal + risk params | Binance order ID, fill price, trade record |

## Directory Structure

```
trading_agents/
├── shared/                    Shared code across all agents
│   ├── llm.py                 Multi-provider LLM wrapper (Gemini, Claude, DeepSeek)
│   ├── binance_client.py      Binance USDT-M Futures API wrapper
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
│   │   └── classify_regime.py LLM + quantitative cross-check regime classification
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
│       ├── fetch_account.py   Binance balance + open orders + timeframe-aware ATR
│       ├── calculate_risk.py  Timeframe-aware ATR-based sizing, SL/TP levels
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
│       ├── trading.html       Dashboard (regime, risk, stats)
│       ├── trades.html        Recent executed trades table
│       ├── signals.html       Recent trade signals table
│       └── strategy.html      Strategy selection history
├── strategies/                TradingView Pine Script strategies (walk-forward validated)
│   ├── ema_trend.pine         4H — pure EMA crossover with ATR trailing stop (OOS Sharpe 1.14)
│   ├── rsi_momentum.pine      4H — RSI 50-line crossover + EMA confirmation (OOS Sharpe 1.63)
│   └── macd_trend.pine        4H — MACD histogram sign-change + EMA filter (portfolio diversifier)
├── tests/
│   └── test_pipeline.py       State schema and mapping tests
├── requirements.txt           Python dependencies
└── run_config.json            Platform run form (mode + dry_run selector)
```

## Configuration

Settings can be configured in two ways:

1. **Settings tab** (recommended) — the **Settings** tab on the agent detail page provides:
   - **LLM Configuration** — select the LLM provider (Gemini, Claude, DeepSeek, Groq, or OpenAI), model, and API key. These are stored in MongoDB's `team_settings` collection and shared with all agent teams.
   - **Trading Controls** — kill switch to enable/disable trading instantly.
   - **Risk Defaults** — max risk per trade, max open positions, max drawdown.
   - **Indicator Periods** — ADX, ATR, BB, EMA, RSI, and Volume MA periods.

   Click **Save Settings** / **Save Trading Settings** to persist everything to MongoDB. These settings survive server restarts.
2. **Environment variables** — set in `.env` as fallback defaults. MongoDB settings take precedence when present.

> **Important:** The **Indicator Periods** in the Settings tab (ADX Period, ATR Period, BB Period, EMA Fast/Mid/Slow, RSI Period, Volume MA Period) are used **only by Pipeline 1's Analyst** for computing the 19 technical indicators that feed into LLM-based regime classification. They have **no effect** on the Pine Script strategies running on TradingView. Each Pine Script strategy has its own independent parameters — see [Pine Script Strategies](#pine-script-strategies) below for details.

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | LLM provider (`gemini`, `claude`, `deepseek`, `groq`, or `openai`) | `gemini` |
| `LLM_MODEL` | Model ID for the selected provider | `gemini-2.5-flash` |
| `GEMINI_API_KEY` | Google Gemini API key | (required if using Gemini) |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key | (required if using Claude) |
| `DEEPSEEK_API_KEY` | DeepSeek API key | (required if using DeepSeek) |
| `GROQ_API_KEY` | Groq API key | (required if using Groq) |
| `OPENAI_API_KEY` | OpenAI API key | (required if using OpenAI) |
| `BINANCE_API_KEY` | Binance USDT-M Futures API key | (required) |
| `BINANCE_API_SECRET` | Binance USDT-M Futures API secret | (required) |
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
| Groq | `llama-3.3-70b-versatile`, `llama-3.1-8b-instant` | Free tier available |
| OpenAI | `gpt-4o`, `gpt-4o-mini`, `o3-mini` | Paid API |

## Running

### Via the Platform UI

1. Upload this team as a ZIP via the Dashboard (with tag `trading`).
2. Once the venv builds, go to the agent detail page.
3. The custom tabs (**Trading**, **Trades**, **Signals**, **Strategy**) will appear automatically, along with the built-in **Settings** tab.
4. Configure the LLM provider, API key, risk parameters, and indicator periods on the **Settings** tab.
5. Click **Run Now** (top right) to open the run modal — select **Pipeline Mode** (`analysis` or `execution`) and **Dry Run**, then click **Run**.
6. Alternatively, use the **Run Analysis** button on the **Trading** tab to quickly trigger an analysis run.
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
- **Kill switch** on the Settings tab instantly disables all trading. State is persisted to MongoDB when Save Trading Settings is clicked.
- **Duplicate detection** ignores identical signals within a 60-second window.
- **Daily trade cap** prevents runaway execution (default: 50 trades/day).
- **Drawdown limit** pauses trading if portfolio drops more than 10% from peak.
- **Max positions** prevents over-exposure (default: 3 concurrent).
- **Exit passthrough** — exit signals are accepted from any strategy that has an open position, even after a strategy switch. This prevents positions from being stranded when the active strategy changes.
- **OCO cleanup on strategy switch** — when the Strategist hot-swaps strategies, all open Binance USDT-M Futures orders from the previous strategy are cancelled automatically to prevent orphaned stop-loss/take-profit orders from interfering.
- **Quantitative cross-check** — the LLM regime classifier is validated against a deterministic indicator-based fallback, reducing the risk of misclassification-driven trades.

## Pine Script Strategies

Three walk-forward validated TradingView strategies in `strategies/` send webhook alerts to this system. Each strategy has its **own parameters defined as TradingView inputs** inside the `.pine` file — these are completely independent from the Indicator Periods in the Settings panel (which only affect the Analyst's regime classification). To change a strategy's trading behavior, edit the `.pine` file directly or override the inputs in TradingView's strategy settings.

> **Note:** All three strategies support **bidirectional** trading (**long and short**) on Binance USDT-M Futures, aligned with the webhook and execution pipeline. All run on the **4H timeframe**.

> **Design philosophy:** Each strategy uses only **2–3 tunable parameters** (plus fixed ATR length). This radical simplification was the key to surviving walk-forward validation — strategies with 5+ parameters consistently overfit during training and degraded on unseen data.

| Strategy | Regime(s) | Timeframe | OOS Sharpe | OOS Return | WF Efficiency | Entry logic (bidirectional) |
|----------|-----------|-----------|------------|------------|---------------|----------------------------|
| `ema_trend` | Uptrend, Downtrend | **4H** | 1.14 | +60.4% | 390% | EMA fast crosses above/below EMA slow → long/short; flips directly on cross |
| `rsi_momentum` | All regimes | **4H** | 1.63 | +101.0% | 137% | RSI crosses above 50 + price > EMA → long; RSI crosses below 50 + price < EMA → short |
| `macd_trend` | Uptrend, Downtrend, Volatile Breakout | **4H** | — | +8.3% | 73% | MACD histogram turns positive + price > EMA → long; histogram turns negative + price < EMA → short |

### Strategy Parameters

#### `ema_trend.pine` (4-hour timeframe) — Walk-Forward Validated

Pure EMA crossover trend strategy. Flips directly between long and short on EMA cross, with ATR trailing stop as risk management. On the execution side, the OCO is placed as a wide 3× ATR "disaster stop" — the Pine trailing stop handles normal exits via webhook.

| Parameter | Default | Description |
|-----------|---------|-------------|
| EMA Fast Length | 12 | Fast EMA for crossover signal |
| EMA Slow Length | 50 | Slow EMA for crossover signal |
| ATR Length | 14 | ATR period for trailing stop |
| ATR Trailing Stop Multiplier | 3.5 | Trailing stop distance as multiple of ATR |

#### `rsi_momentum.pine` (4-hour timeframe) — Walk-Forward Validated

RSI 50-line crossover with EMA trend confirmation. The strongest standalone performer in walk-forward testing. Works across all market regimes and is the recommended default strategy.

| Parameter | Default | Description |
|-----------|---------|-------------|
| RSI Length | 14 | RSI lookback period |
| EMA Length | 50 | EMA for trend direction confirmation |
| ATR Length | 14 | ATR period for trailing stop |
| ATR Trailing Stop Multiplier | 3.0 | Trailing stop distance as multiple of ATR |

#### `macd_trend.pine` (4-hour timeframe) — Portfolio Diversifier

MACD histogram sign-change with EMA trend filter. While not the strongest standalone performer, it provides portfolio diversification due to uncorrelated signal generation compared to EMA and RSI-based strategies.

| Parameter | Default | Description |
|-----------|---------|-------------|
| MACD Fast Length | 12 | Fast EMA for MACD calculation |
| MACD Slow Length | 26 | Slow EMA for MACD calculation |
| MACD Signal Length | 9 | Signal line EMA period |
| ATR Length | 14 | ATR period for trailing stop |
| ATR Trailing Stop Multiplier | 3.0 | Trailing stop distance as multiple of ATR |

Each strategy sends a JSON webhook payload containing `strategy_name`, `action`, `ticker`, `price`, and a shared `secret` for authentication.

## Strategy Backtest — Walk-Forward Analysis Engine

The platform includes a walk-forward backtesting engine (`agent_platform/api/routes/backtest.py`) that translates all five Pine Script strategies into Python and runs them against historical Binance data. The purpose is to expose curve-fitting: comparing what a retail backtest shows (in-sample, optimised on all data) vs. what actually happens on unseen data (out-of-sample, blind-tested).

Access the backtest tool from the **Backtest** tab under Dashboard.

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

### Binance USDT-M Futures fees

Walk-forward runs deduct per-trade costs using the `exchange_fee` and `slippage` fields (percent **per position change**, applied as in `backtest.py`). For Binance USDT-M Futures, use fee tiers consistent with published rates:

| | Rate |
|---|------|
| Maker | **0.02%** |
| Taker | **0.05%** |
| Typical blended (pay fees with BNB) | **~0.04%** average |

Example: model mixed execution with `"exchange_fee": 0.04` (meaning **0.04%** per the engine’s percent convention). Adjust upward if you assume mostly taker fills.

### Strategies (Python Translations)

Each Pine Script strategy is translated to Python with the same core logic (including **long and short**). All strategies run on the **4H timeframe** with only 2–3 tunable parameters each:

| Strategy | Timeframe | Indicators | Entry | Exit | Optimised Parameters |
|----------|-----------|------------|-------|------|---------------------|
| `ema_trend` | **4h** | EMA fast, EMA slow, ATR | EMA fast crosses above slow → long; crosses below → short; flips directly | ATR trailing stop or opposite EMA cross | `ema_fast`, `ema_slow`, `atr_trail` |
| `rsi_momentum` | **4h** | RSI, EMA, ATR | RSI crosses above 50 + price > EMA → long; RSI crosses below 50 + price < EMA → short | ATR trailing stop or opposite RSI cross | `rsi_len`, `ema_len`, `atr_trail` |
| `macd_trend` | **4h** | MACD histogram, EMA, ATR | MACD histogram turns positive + price > EMA → long; histogram turns negative + price < EMA → short | ATR trailing stop or opposite MACD cross | `macd_fast`, `macd_slow`, `atr_trail` |

Legacy strategies (`trend_following`, `mean_reversion`, `swing_momentum`, `pullback`, `breakout`, `accumulation`) are still available in the backtest engine for comparison but are no longer seeded as defaults.

### Technical Indicators

All indicators are implemented in pure numpy/pandas to avoid external TA library dependencies:

| Function | Description |
|----------|-------------|
| `_ema` | Exponential Moving Average via `pandas.ewm` |
| `_sma` | Simple Moving Average via rolling window |
| `_rsi` | Relative Strength Index (rolling mean of gains vs. losses) |
| `_atr` | Average True Range (max of high−low, \|high−prev_close\|, \|low−prev_close\|) |
| `_bb` | Bollinger Bands (middle ± n × rolling std) |
| `_adx` | Average Directional Index (+DI, −DI, DX, smoothed ADX) |
| `_macd` | MACD histogram (fast EMA − slow EMA − signal EMA) |
| `_vwap` | Rolling Volume-Weighted Average Price over a lookback period |
| `_donchian` | Donchian Channel (rolling highest high, lowest low, midline) |

### Optimisation

Each fold performs a grid search over the strategy's parameter space:

- Iterates every parameter combination in the grid
- Executes the strategy, computes per-candle returns with transaction costs (exchange fee + slippage deducted on every position change)
- Calculates the annualised Sharpe ratio (annualisation factor depends on the timeframe: **15m:** 4 × 24 × 365 = **35,040** periods/year → √35,040; **2h:** √4,380; **4h:** √2,190)
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
  "strategy": "trend_following",
  "exchange_fee": 0.04,
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

The Backtest tab renders four sections after analysis completes:

1. **Walk-Forward Timeline** — horizontal bar chart showing each fold's train (blue) and blind test (orange) windows
2. **Parameter Shift Table** — shows how the "optimal" parameters change across folds, proving that no single fixed set works across all market regimes
3. **Illusion vs. Reality** — side-by-side metric cards (total return, Sharpe, max drawdown, trade count) for in-sample vs. out-of-sample, plus degradation figures
4. **Equity Curve** — overlaid line chart comparing the retail backtest equity (in-sample) against the walk-forward equity (out-of-sample), with shaded bands marking each blind test window
