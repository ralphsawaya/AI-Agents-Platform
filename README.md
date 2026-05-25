# AI Agent Management Platform

A production-grade web platform for managing the full lifecycle of multi-agent AI teams. Upload agent team packages as `.zip` files, and the platform validates, registers, executes, schedules, monitors, and visualises your agents in real time.

## Prerequisites

- **Python 3.11+**
- **MongoDB** — local deployment at `127.0.0.1:55440` (Atlas-compatible; supports vector search for Trip Agents)

### MongoDB

The platform uses a **single MongoDB instance** at:

```
mongodb://127.0.0.1:55440/?directConnection=true
```

Two databases on that instance:

| Database | Used by |
|----------|---------|
| `agent_platform` | Platform metadata, runs, schedules, team settings |
| `trip_data` | Trip Agents inventory, chat, reservations, vector indexes |

Set both `MONGODB_URI` and `ATLAS_MONGODB_URI` to this connection string in `.env` (see `.env.example`). StrategyGPT collections also live on the same instance under `agent_platform`.

## Project Structure

```
AI-Agents-Platform/
├── agent_platform/          # The platform itself (FastAPI app) — see agent_platform/README.md
│   ├── api/                 # REST & WebSocket routes
│   ├── core/                # Business logic (executor, monitor, scheduler…)
│   ├── db/                  # MongoDB repositories & indexes
│   ├── ui/                  # Jinja2 templates, CSS, JS
│   └── agents_store/        # Extracted agent packages (auto-managed)
└── teams/                   # Your agent team workspaces
    ├── trip_agents/         # Trip planning multi-agent team
    └── strategygpt_agents/  # Lead sourcing, qualification, and voice outreach
```

Each folder inside `teams/` is a **team workspace** — a place to develop and package an agent team. When ready, run `build_zip.py` inside the workspace to produce a `.zip` ready for upload.

### Included agent teams

| Team | Purpose | Documentation |
|------|---------|---------------|
| [`trip_agents/`](teams/trip_agents/) | Conversational trip search, booking, and reservations (flights, hotels, cars) | [teams/trip_agents/README.md](teams/trip_agents/README.md) |
| [`strategygpt_agents/`](teams/strategygpt_agents/) | Lead sourcing, qualification, and AI voice outreach for SMB website sales | [teams/strategygpt_agents/README.md](teams/strategygpt_agents/README.md) |

Trip Agents adds custom UI tabs (Trip Planner, Reservations), a dedicated REST API at `/api/trip/{agent_id}`, and stores domain data in the `trip_data` database on the same MongoDB instance (`127.0.0.1:55440`). StrategyGPT adds `/api/strategygpt/{agent_id}` routes and its own MongoDB collections (`strategygpt_*`) on `agent_platform`.

## Setup & Run

```bash
# Clone and enter the project
cd AI-Agents-Platform

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r agent_platform/requirements.txt

# Create a .env file from the template and add your API keys
cp .env.example .env
# Both MongoDB variables default to mongodb://127.0.0.1:55440/?directConnection=true
# Edit .env to add LLM provider keys and VOYAGE_AI_API_KEY (Trip Agents).

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

Agent teams can ship custom UI tabs that appear on the agent detail page under a **Dashboard** parent tab. When the team has custom tabs, a "Dashboard" entry is added to the main tab bar; clicking it reveals a secondary sub-tab bar containing the team's custom tabs. Define a `ui/tabs.json` file in the zip root:

```json
{
  "tabs": [
    { "id": "trip_planner",  "label": "Trip Planner" },
    { "id": "reservations",  "label": "Reservations" }
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
cd teams/trip_agents
python3 build_zip.py
# → creates trip_agents.zip ready for upload
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

### Cursor MCP (MongoDB)

The project includes one MongoDB MCP server for local development: **`MongoDB-Atlas-Local`**. **Never commit credentials in `.cursor/mcp.json`.** The connection string is loaded from your `.env` file via [`.cursor/run-mongodb-mcp.sh`](.cursor/run-mongodb-mcp.sh):

| MCP server | `.env` variables (first match wins) | Purpose |
|------------|-------------------------------------|---------|
| `MongoDB-Atlas-Local` | `ATLAS_MONGODB_URI`, then `MONGODB_URI` | Local MongoDB at `127.0.0.1:55440` (`agent_platform`, `trip_data`, etc.) |

Copy [`.cursor/mcp.json.example`](.cursor/mcp.json.example) to `.cursor/mcp.json` if needed. Both URI variables default to `mongodb://127.0.0.1:55440/?directConnection=true`. To sync `ATLAS_MONGODB_URI` into Trip Agents Settings, run [`scripts/update-atlas-uri.sh`](scripts/update-atlas-uri.sh).

## Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│                     Browser UI                       │
│  Dashboard │ Agent Detail (+Custom Tabs) │ Monitor   │
│  Scheduler │ Settings │ Graph                        │
└─────────────────────┬────────────────────────────────┘
                      │ HTTP / WebSocket
┌─────────────────────▼────────────────────────────────┐
│                  FastAPI Application                 │
│  REST Routes │ WebSocket │ SSR                       │
│  /api/trip · /api/strategygpt (team-specific)        │
└──────┬──────────────┬────────────────────────────────┘
       │              │
┌──────▼──────┐ ┌─────▼────────────────────────────────┐
│  Core Logic │ │           Data Layer (Motor)          │
│  validator  │ │  agent_repo │ run_repo │ sched_repo   │
│  executor   │ │  relationship_repo │ indexes          │
│  scheduler  │ └─────────────────────┬────────────────┘
│  monitor    │                       │
│  graph_bld  │               ┌───────▼───────────────────────────┐
│  venv_mgr   │               │  MongoDB @ 127.0.0.1:55440         │
└──────┬──────┘               │  agent_platform · trip_data        │
       │                      └───────────────────────────────────┘
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
- **Settings** — LLM provider/model selection and API key management for the team, persisted to MongoDB (`team_settings` collection). Supported providers: Google Gemini (default), Anthropic Claude, DeepSeek, Groq, and OpenAI. API keys can be toggled between masked and visible using the eye icon. All teams share the same LLM selection UI; each team's settings are stored independently by agent ID. This tab is built-in and appears automatically for every agent team — no configuration needed.
- **Dashboard** — parent tab that groups all custom team-specific tabs as subsections. When clicked, a secondary navigation bar appears below the main tabs showing the team's custom tabs (e.g. the trip team's Dashboard contains Trip Planner and related sub-tabs). The Dashboard tab and its sub-tab bar share a distinct tinted background with an accent border to visually convey the parent–child hierarchy. Custom tabs are loaded as plugins from `ui/tabs/` in the team package.
- **Danger Zone** — rebuild virtual environment (re-install dependencies) and permanent deletion with confirmation

### Monitor
Live table of all running agent teams showing CPU%, memory (MB), elapsed time, and last log line. Fixed-layout table with no flicker. Updates in real time via WebSocket with 20-second REST fallback polling.

### Scheduler
Global schedule management across all agent teams. Toggle enable/disable, view next run times.

### Settings
Platform-level settings. Currently includes **Dashboard Visibility** — toggle which agent teams are shown or hidden on the Dashboard. Hidden teams remain accessible via direct links and other pages; only the Dashboard listing is filtered. Visibility preferences are persisted in MongoDB.

### Relationship Graph
Interactive Cytoscape.js visualisation of inter-agent relationships. Three layout options (hierarchical, force-directed, circular). Click nodes to navigate to agent details.

## Configuration

All settings are in `agent_platform/config.py` and overridable via `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URI` | `mongodb://127.0.0.1:55440/?directConnection=true` | Platform database connection (`agent_platform`) |
| `MONGODB_DB_NAME` | `agent_platform` | Platform database name |
| `ATLAS_MONGODB_URI` | `mongodb://127.0.0.1:55440/?directConnection=true` | Trip Agents domain database (`trip_data`); same MongoDB instance |
| `VOYAGE_AI_API_KEY` | *(empty)* | Voyage AI embeddings for Trip Agents vector search |
| `AGENTS_STORE_PATH` | `agent_platform/agents_store` | Agent file storage path |
| `DEFAULT_TIMEOUT_SECONDS` | `300` | Max execution time per run |
| `FAILURE_ALERT_THRESHOLD` | `3` | Consecutive failures before alert |
| `LOG_RETENTION_DAYS` | `30` | TTL for run log documents |
| `PORT` | `8000` | Server port |
| `GEMINI_API_KEY` | *(empty)* | For agent teams using Google Gemini (default LLM) |
| `GROQ_API_KEY` | *(empty)* | Forwarded to all agent subprocesses |
| `ANTHROPIC_API_KEY` | *(empty)* | For agent teams using Claude |

## Technical Stack

- **FastAPI** with Jinja2 server-rendered UI
- **MongoDB** via Motor (async driver) — `127.0.0.1:55440`
- **APScheduler** with MongoDBJobStore
- **Python subprocess** with isolated venvs per team
- **WebSockets** for live log streaming and monitor updates
- **Cytoscape.js** for graph visualisation
- **highlight.js** for code syntax highlighting
- **marked.js** for Markdown rendering
- **psutil** for CPU/memory resource monitoring
- **Python ast** for static LangGraph node/tool detection
