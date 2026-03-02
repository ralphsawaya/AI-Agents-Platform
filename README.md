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
    ├── sample_agents/        # Example team (my_first_agents)
    └── team_ab_agents/       # Example two-agent pipeline (Agent A + Agent B)
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

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Browser UI                           │
│  Dashboard │ Agent Detail │ Monitor │ Scheduler │ Graph │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP / WebSocket
┌─────────────────────▼───────────────────────────────────┐
│                  FastAPI Application                    │
│  REST Routes │ WebSocket Endpoints │ Jinja2 Renderer    │
└──────┬──────────────┬───────────────────────────────────┘
       │              │
┌──────▼──────┐ ┌─────▼──────────────────────────────────┐
│  Core Logic │ │           Data Layer (Motor)            │
│  validator  │ │  agent_repo │ run_repo │ schedule_repo  │
│  executor   │ │  relationship_repo │ indexes            │
│  scheduler  │ └─────────────────────┬──────────────────┘
│  monitor    │                       │
│  graph_bld  │               ┌───────▼───────┐
│  venv_mgr   │               │   MongoDB 8.0 │
└──────┬──────┘               └───────────────┘
       │
┌──────▼────────────────────┐
│  agents_store/ (on disk)  │
│  <uuid>/ per agent team   │
│    ├── extracted files    │
│    ├── .venv/             │
│    └── logs/<run_id>.log  │
└───────────────────────────┘
```

## UI Sections

### Dashboard
Summary cards (total teams, running, scheduled, errored), card/table toggle, search and filter by status/tags/name, upload modal with drag-and-drop.

### Agent Detail
Tabbed interface:
- **Overview** — stat cards, detected LangGraph nodes (indigo pills), tools (green pills), agent folders (amber pills), and a rendered Markdown description
- **Files** — read-only source file browser with syntax highlighting (excludes `.venv`, caches, and build artifacts)
- **Runs** — paginated run history with log viewer and live WebSocket tail
- **Schedules** — create/edit/delete cron, interval, or one-time schedules
- **Danger Zone** — permanent deletion with confirmation

### Monitor
Live table of all running agent teams showing CPU%, memory (MB), elapsed time, and last log line. Fixed-layout table with no flicker. Updates in real time via WebSocket with 20-second REST fallback polling.

### Scheduler
Global schedule management across all agent teams. Toggle enable/disable, view next run times.

### Relationship Graph
Interactive Cytoscape.js visualisation of inter-agent relationships. Three layout options (hierarchical, force-directed, circular). Click nodes to navigate to agent details.

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
