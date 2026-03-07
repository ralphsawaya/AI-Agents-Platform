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

1. **The Analyst** pulls 4H and 1H BTC/USDT candles from Binance, computes technical indicators (ADX, ATR, Bollinger Bands, EMAs, RSI, MACD, volume ratios), and asks Gemini to classify the current market regime as one of:
   - `trending_up` — strong uptrend, ADX > 25, EMA alignment bullish
   - `trending_down` — strong downtrend, ADX > 25, EMA alignment bearish
   - `ranging` — low ADX, narrow Bollinger Bands, sideways price action
   - `high_volatility` — ATR spike, wide Bollinger Bands, unstable direction

2. **The Strategist** maps the regime to the best-fit Pine Script strategy:
   - Trending regimes --> `trend_following`
   - Ranging --> `mean_reversion`
   - High volatility --> `scalping`

   For edge cases (low confidence, regime transitions), Gemini provides a second opinion before committing. The active strategy is stored in MongoDB.

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

### Stage 3 — Gemini classifies the regime

All 19 indicators are formatted into a structured prompt and sent to Gemini. Gemini reads the numbers and returns:
- **Regime** — one of `trending_up`, `trending_down`, `ranging`, `high_volatility`
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
│   ├── llm.py                 Google Gemini wrapper
│   ├── binance_client.py      Binance Spot API wrapper
│   ├── indicators.py          Technical indicator calculations (ta library)
│   ├── models.py              Data models (MarketRegime, TradeSignal, RiskParams, etc.)
│   ├── config.py              Trading pair, risk limits, indicator periods
│   ├── mongo.py               MongoDB collection accessors
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
│       ├── trading.html       Kill switch, regime overview, risk state, indicators
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

All configuration is injected via environment variables by the platform (AI-Agents-Platform/teams/trading_agents/shared/config.py):

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key for Analyst and Strategist | (required) |
| `BINANCE_API_KEY` | Binance Spot API key | (required) |
| `BINANCE_API_SECRET` | Binance Spot API secret | (required) |
| `TRADING_PAIR` | Symbol to trade | `BTCUSDT` |
| `MAX_RISK_PER_TRADE` | Fraction of portfolio risked per trade | `0.02` (2%) |
| `MAX_OPEN_POSITIONS` | Maximum concurrent positions | `3` |
| `MAX_DRAWDOWN` | Pause trading above this drawdown | `0.10` (10%) |
| `LLM_MODEL` | Google Gemini model ID | `gemini-2.5-flash` |

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
- **Kill switch** on the Trading tab instantly disables all trading.
- **Duplicate detection** ignores identical signals within a 60-second window.
- **Daily trade cap** prevents runaway execution (default: 50 trades/day).
- **Drawdown limit** pauses trading if portfolio drops more than 10% from peak.
- **Max positions** prevents over-exposure (default: 3 concurrent).

## Pine Script Strategies

Three TradingView strategies in `strategies/` send webhook alerts to this system:

| Strategy | Regime | Timeframe | Entry Logic |
|----------|--------|-----------|-------------|
| `trend_following` | Trending | 4H | EMA(9/21) crossover + ADX > 25 + MACD confirmation |
| `mean_reversion` | Ranging | 4H | Bollinger Band bounce + RSI oversold/overbought + volume |
| `scalping` | High volatility | 1H | VWAP + EMA(9) + volume spike, tight SL/TP |

Each strategy sends a JSON webhook payload containing `strategy_name`, `action`, `ticker`, `price`, and a shared `secret` for authentication.
