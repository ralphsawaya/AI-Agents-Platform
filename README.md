# AI Agent Management Platform

A production-grade web platform for managing the full lifecycle of multi-agent AI teams. Upload agent team packages as `.zip` files, and the platform validates, registers, executes, schedules, monitors, and visualises your agents in real time.

## Prerequisites

- **Python 3.11+**
- **MongoDB 8.0** (running locally or via Docker)
- **Docker** (optional — for running MongoDB)

### Quick MongoDB Setup with Docker

```bash
docker run -d --name mongodb -p 27017:27017 mongo:8.0
```

## Project Structure

```
AI-Agents-Platform/
├── agent_platform/          # The platform itself (FastAPI app)
│   ├── api/                 # REST & WebSocket routes
│   ├── core/                # Business logic (executor, monitor, scheduler…)
│   ├── db/                  # MongoDB repositories & indexes
│   ├── ui/                  # Jinja2 templates, CSS, JS
│   └── agents_store/        # Extracted agent packages (auto-managed)
└── teams/                   # Your agent team workspaces
    ├── sample_agents/       # Example team (my_first_agents)
    ├── team_ab_agents/      # Two-agent pipeline (Summarise + Title)
    └── trading_agents/      # Autonomous BTC/USDT trading system (4 agents)
```

Each folder inside `teams/` is a **team workspace** — a place to develop and package an agent team. When ready, run `build_zip.py` inside the workspace to produce a `.zip` ready for upload.

## Setup & Run

```bash
# Clone and enter the project
cd AI-Agents-Platform

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r agent_platform/requirements.txt

# Create a .env file with your API keys and settings
cat > .env << 'EOF'
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=agent_platform
PORT=8000
GROQ_API_KEY=your_groq_api_key_here
EOF

# Initialise MongoDB indexes
python -m agent_platform.db.init_indexes

# Start the platform
python -m agent_platform.main
```

The platform will be available at **http://localhost:8000**.

## How to Prepare and Upload an Agent Team

### Required Zip Structure

Your `.zip` must contain **exactly one root folder** (the team name) with this layout:

```
my_team/
├── README.md                   # Optional — shown in the Overview tab
├── run_config.json             # Optional — defines a custom Run input form
├── requirements.txt            # Top-level dependencies
├── ui/                         # Optional — custom UI tabs (plugin system)
│   ├── tabs.json               # Tab definitions (id + label)
│   └── tabs/                   # One HTML fragment per tab
│       └── my_tab.html         # Self-contained HTML + <style> + <script>
├── shared/                     # Shared utilities across all agents
│   ├── __init__.py
│   ├── config.py
│   ├── logger.py
│   ├── utils.py
│   ├── llm.py
│   └── models.py
├── agent_a/                    # One or more agent_* folders
│   ├── agent.py                # REQUIRED
│   ├── main.py                 # REQUIRED
│   ├── state.py                # REQUIRED
│   ├── requirements.txt        # REQUIRED
│   ├── config.yaml             # REQUIRED
│   ├── nodes/
│   ├── edges/
│   ├── tools/
│   ├── memory/
│   └── prompts/
├── orchestrator/               # Wires agents together via LangGraph
│   ├── main.py                 # REQUIRED — platform entry point
│   ├── graph.py                # REQUIRED
│   └── state.py                # REQUIRED
├── tests/
├── data/
│   ├── inputs/
│   └── outputs/
└── checkpoints/
```

### Optional: `run_config.json`

Define a custom input form for the **Run** modal instead of the default raw-JSON textarea:

```json
{
  "fields": [
    {
      "name": "text",
      "label": "Text Paragraph (max 500 words)",
      "type": "textarea",
      "placeholder": "Paste your text here…",
      "required": true,
      "rows": 10,
      "max_words": 500
    }
  ]
}
```

Supported field types: `textarea`, `text`, `number`, `select`.

### Optional: `ui/tabs.json` (Custom Tabs Plugin)

Agent teams can ship custom UI tabs that appear on the agent detail page alongside the standard tabs (Overview, Files, Runs, Schedules, Danger Zone). Define a `ui/tabs.json` file in the zip root:

```json
{
  "tabs": [
    { "id": "trading",  "label": "Trading" },
    { "id": "trades",   "label": "Trades" }
  ]
}
```

For each tab, create a matching HTML fragment at `ui/tabs/<id>.html`. Each fragment is self-contained and can include its own `<style>` and `<script>` blocks:

```html
<style>
.my-card { padding: 16px; background: var(--surface); border-radius: 8px; }
</style>

<h3>My Custom Tab</h3>
<div class="my-card" id="my-data">Loading…</div>

<script>
(function() {
    async function loadData() {
        const res = await API.get('/api/my-endpoint');
        if (res.success) {
            document.getElementById('my-data').innerHTML = res.data;
        }
    }
    loadData();
    setInterval(loadData, 15000);
})();
</script>
```

Scripts are executed automatically after injection. Use IIFEs to avoid polluting the global scope. The platform's `API` helper and `toast()` function are available globally.

### Optional: `README.md`

Any `README.md` in the zip root is automatically read and rendered as the **Description** in the Overview tab, using full Markdown formatting.

### Upload Steps

1. Open the platform at `http://localhost:8000`
2. Click **Upload Agent** on the Dashboard
3. Drag and drop your `.zip` (or click to browse)
4. Optionally enter a name, description, and tags
5. Click **Upload** — the platform validates the structure and shows errors if any
6. The team appears on the dashboard and a virtual environment is built in the background

### Building a Zip from a Team Workspace

Each team workspace under `teams/` includes a `build_zip.py` script:

```bash
cd teams/team_ab_agents
python3 build_zip.py
# → creates team_ab.zip ready for upload
```

## Development Workflow

The project has two copies of each agent team's code:

| Location | Purpose |
|----------|---------|
| `teams/<team_name>/` | Development source — edit code here |
| `agent_platform/agents_store/<agent_id>/<team_name>/` | Runtime copy — the platform runs agents from here |

When you upload a `.zip`, the platform extracts it into `agents_store/` under a unique agent ID and builds a dedicated venv there. The platform always executes code from `agents_store/`, never from `teams/`.

**During development with Cursor**, a project rule (`.cursor/rules/sync-team-to-agents-store.mdc`) ensures that every edit made to a file under `teams/` is automatically applied to the corresponding file in `agents_store/`. This includes `.env` files, source code, config files, and templates — so changes take effect immediately without re-uploading a zip.

If you're not using Cursor, you'll need to either re-zip and re-upload, or manually copy changed files into the `agents_store/` directory.

## Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│                     Browser UI                       │
│  Dashboard │ Agent Detail (+Custom Tabs) │ Monitor   │
│  Scheduler │ Graph                                   │
└─────────────────────┬────────────────────────────────┘
                      │ HTTP / WebSocket
┌─────────────────────▼────────────────────────────────┐
│                  FastAPI Application                 │
│  REST Routes │ Webhook API │ Trading API │ WS │ SSR  │
└──────┬──────────────┬────────────────────────────────┘
       │              │
┌──────▼──────┐ ┌─────▼────────────────────────────────┐
│  Core Logic │ │           Data Layer (Motor)          │
│  validator  │ │  agent_repo │ run_repo │ sched_repo   │
│  executor   │ │  relationship_repo │ indexes          │
│  scheduler  │ └─────────────────────┬────────────────┘
│  monitor    │                       │
│  graph_bld  │               ┌───────▼───────┐
│  venv_mgr   │               │   MongoDB 8.0 │
└──────┬──────┘               └───────────────┘
       │
┌──────▼────────────────────┐
│  agents_store/ (on disk)  │
│  <uuid>/ per agent team   │
│    ├── extracted files    │
│    ├── ui/tabs/ (plugins) │
│    ├── .venv/             │
│    └── logs/<run_id>.log  │
└───────────────────────────┘
```

## UI Sections

### Dashboard
Summary cards (total teams, running, scheduled, errored), card/table toggle, search and filter by status/tags/name, upload modal with drag-and-drop.

### Agent Detail
Tabbed interface with standard tabs for all teams, plus optional custom tabs per team:
- **Overview** — stat cards, detected LangGraph nodes (indigo pills), tools (green pills), agent folders (amber pills), rendered Markdown description, and interactive pipeline graph
- **Files** — read-only source file browser with syntax highlighting (excludes `.venv`, caches, and build artifacts)
- **Runs** — paginated run history (15 per page, last 100 runs) with inline log viewer and live WebSocket tail
- **Schedules** — create/edit/delete cron, interval, or one-time schedules
- **Custom Tabs** — team-specific tabs loaded as plugins from `ui/tabs/` in the team package (e.g. the trading team ships Trading, Trades, Signals, and Strategy tabs with LLM provider selection, risk parameters, and trading settings persisted to MongoDB)
- **Danger Zone** — rebuild virtual environment (re-install dependencies) and permanent deletion with confirmation

### Monitor
Live table of all running agent teams showing CPU%, memory (MB), elapsed time, and last log line. Fixed-layout table with no flicker. Updates in real time via WebSocket with 20-second REST fallback polling.

### Scheduler
Global schedule management across all agent teams. Toggle enable/disable, view next run times.

### Relationship Graph
Interactive Cytoscape.js visualisation of inter-agent relationships. Three layout options (hierarchical, force-directed, circular). Click nodes to navigate to agent details.

### Strategy Backtest
Walk-forward analysis engine at `/strategy-backtest`. Select a strategy, date range, and window sizes — the engine fetches OHLCV data from Binance (cached in MongoDB), runs a rolling train/blind-test optimisation, and streams fold-by-fold progress back to the browser. See [Strategy Backtest — Walk-Forward Analysis Engine](#strategy-backtest--walk-forward-analysis-engine) below for full details.

## Strategy Backtest — Walk-Forward Analysis Engine

The platform includes a walk-forward backtesting engine (`agent_platform/api/routes/backtest.py`) that translates the three Pine Script strategies of the trading agents team into Python and runs them against historical Binance data. The purpose is to expose curve-fitting: comparing what a retail backtest shows (in-sample, optimised on all data) vs. what actually happens on unseen data (out-of-sample, blind-tested).

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
| `_atr` | Average True Range (max of high−low, \|high−prev_close\|, \|low−prev_close\|) |
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

## Configuration

All settings are in `agent_platform/config.py` and overridable via `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGODB_DB_NAME` | `agent_platform` | Database name |
| `AGENTS_STORE_PATH` | `agent_platform/agents_store` | Agent file storage path |
| `DEFAULT_TIMEOUT_SECONDS` | `300` | Max execution time per run |
| `FAILURE_ALERT_THRESHOLD` | `3` | Consecutive failures before alert |
| `LOG_RETENTION_DAYS` | `30` | TTL for run log documents |
| `PORT` | `8000` | Server port |
| `GROQ_API_KEY` | *(empty)* | Forwarded to all agent subprocesses |
| `ANTHROPIC_API_KEY` | *(empty)* | For agent teams using Claude |
| `BINANCE_API_KEY` | *(empty)* | For the trading agents team |
| `BINANCE_API_SECRET` | *(empty)* | For the trading agents team |
| `TRADINGVIEW_WEBHOOK_SECRET` | *(empty)* | Webhook authentication secret |
| `TRADING_ENABLED` | `true` | Global trading kill switch (also persisted to MongoDB via Trading tab settings) |
| `TRADING_DRY_RUN` | `true` | Simulate trades without real orders |
| `TRADING_MAX_DAILY_TRADES` | `50` | Daily trade limit |

## Technical Stack

- **FastAPI** with Jinja2 server-rendered UI
- **MongoDB 8.0** via Motor (async driver)
- **APScheduler** with MongoDBJobStore
- **Python subprocess** with isolated venvs per team
- **WebSockets** for live log streaming and monitor updates
- **Cytoscape.js** for graph visualisation
- **highlight.js** for code syntax highlighting
- **marked.js** for Markdown rendering
- **psutil** for CPU/memory resource monitoring
- **Python ast** for static LangGraph node/tool detection
