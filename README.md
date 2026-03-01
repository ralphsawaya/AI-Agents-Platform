# AI Agent Management Platform

A production-grade web platform for managing the full lifecycle of LangChain/LangGraph AI agents. Upload agent packages as `.zip` files, and the platform validates, registers, executes, schedules, monitors, and visualises relationships between your agents.

## Prerequisites

- **Python 3.11+**
- **MongoDB 8.0** (running locally or via Docker)
- **Docker** (optional — for running MongoDB)

### Quick MongoDB Setup with Docker

```bash
docker run -d --name mongodb -p 27017:27017 mongo:8.0
```

## Setup & Run

```bash
# Clone and enter the project
cd AI-Agents-Platform

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r agent_platform/requirements.txt

# (Optional) Create a .env file to override defaults
cat > .env << 'EOF'
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=agent_platform
PORT=8000
EOF

# Initialise MongoDB indexes (standalone)
python -m agent_platform.db.init_indexes

# Start the platform
python -m agent_platform.main
```

The platform will be available at **http://localhost:8000**.

## How to Prepare and Upload a Valid Agent Zip

Your `.zip` file must contain **exactly one root folder** with this structure:

```
my_agents/
├── shared/                     # Shared utilities
│   ├── __init__.py
│   ├── models.py
│   ├── config.py
│   ├── logger.py
│   ├── utils.py
│   └── llm.py
├── agent_alpha/                # At least one agent_* folder
│   ├── __init__.py
│   ├── main.py                 # REQUIRED
│   ├── agent.py                # REQUIRED
│   ├── state.py                # REQUIRED
│   ├── nodes/
│   ├── edges/
│   ├── tools/
│   ├── memory/
│   ├── prompts/
│   ├── requirements.txt        # REQUIRED
│   └── config.yaml             # REQUIRED
├── orchestrator/
│   ├── __init__.py
│   ├── main.py
│   ├── graph.py                # REQUIRED
│   └── state.py                # REQUIRED
├── tests/
├── data/
│   ├── inputs/
│   └── outputs/
├── checkpoints/
└── requirements.txt            # Top-level
```

A pre-built sample is included at `sample_agents/my_first_agents.zip`.

### Upload Steps

1. Open the platform at `http://localhost:8000`
2. Click **Upload Agent** on the Dashboard
3. Drag and drop your `.zip` file (or click to browse)
4. Optionally set a name, description, and tags
5. Click **Upload** — the platform validates the structure and shows errors if any
6. On success, the agent appears on the dashboard. The platform creates an isolated virtual environment in the background

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
│  graph_builder                ┌─────▼─────┐
│  venv_manager │               │ MongoDB   │
└──────┬────────┘               │ 8.0       │
       │                        └───────────┘
┌──────▼────────────────────┐
│  agents_store/ (on disk)  │
│  <uuid>/ per agent        │
│    ├── extracted files    │
│    ├── .venv/             │
│    └── logs/<run_id>.log  │
└───────────────────────────┘
```

## UI Sections

### Dashboard
Summary cards (total, running, scheduled, errored agents), card/table toggle, search and filter by status/tags/name, upload modal with drag-and-drop, real-time validation feedback.

### Agent Detail
Tabbed interface with:
- **Overview**: metadata, detected LangGraph nodes and tools, config display
- **Files**: read-only file browser with syntax highlighting
- **Runs**: paginated run history with log viewer and live tail via WebSocket
- **Schedules**: create/edit/delete schedules linked to this agent
- **Danger Zone**: permanent deletion with confirmation

### Monitor
Live table of all running agents showing CPU%, memory, elapsed time, and last log line. Updates in real-time via WebSocket. Alert banners for agents exceeding the failure threshold.

### Scheduler
Global schedule management across all agents. Create cron, interval, or one-time schedules. Toggle enable/disable, view next run times.

### Relationship Graph
Interactive Cytoscape.js visualisation of agent relationships. Three layout options (hierarchical, force-directed, circular). Click nodes to navigate to agent details. Edges show relationship type and detection method.

## Configuration

All settings are in `agent_platform/config.py` and overridable via `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGODB_DB_NAME` | `agent_platform` | Database name |
| `AGENTS_STORE_PATH` | `agent_platform/agents_store` | Agent file storage |
| `DEFAULT_TIMEOUT_SECONDS` | `300` | Max execution time per run |
| `FAILURE_ALERT_THRESHOLD` | `3` | Consecutive failures before alert |
| `LOG_RETENTION_DAYS` | `30` | TTL for run documents |
| `PORT` | `8000` | Server port |

## Technical Stack

- **FastAPI** with Jinja2 server-rendered UI
- **MongoDB 8.0** via Motor (async driver)
- **APScheduler** with MongoDBJobStore
- **Python subprocess** with isolated venvs
- **WebSockets** for live monitoring
- **Cytoscape.js** for graph visualisation
- **highlight.js** for code syntax highlighting
- **psutil** for resource monitoring
- **Python ast** for static source analysis
