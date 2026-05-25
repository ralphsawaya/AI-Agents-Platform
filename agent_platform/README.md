# Agent Platform

FastAPI application that hosts, executes, and monitors uploaded multi-agent teams.

For **setup, MongoDB configuration, and development workflow**, see the [repository root README](../README.md).

## Layout

```
agent_platform/
├── main.py              # Application entry point
├── config.py            # Platform settings (MongoDB URI, paths, timeouts)
├── api/routes/          # REST & WebSocket endpoints
│   ├── agents.py        # Upload, list, delete agent teams
│   ├── execution.py     # Run agents, stream logs
│   ├── trip.py          # Trip Agents API (/api/trip/{agent_id})
│   ├── strategygpt.py   # StrategyGPT API (/api/strategygpt/{agent_id})
│   ├── team_settings.py # Per-agent LLM keys and integration settings
│   └── …
├── core/                # Executor, scheduler, monitor, validator, venv manager
├── db/                  # Motor client, repositories, indexes
├── ui/                  # Jinja2 templates, CSS, JS
└── agents_store/        # Runtime copies of uploaded teams (do not edit by hand)
    └── <agent_id>/
        ├── .venv/       # Per-team virtual environment
        ├── logs/        # Run logs
        └── <team_name>/ # Extracted team package + README.md (Overview tab)
```

## agents_store

The platform **always runs code from `agents_store/`**, not from `teams/`. Each uploaded zip is extracted under a UUID folder and gets its own venv.

| Agent ID | Team | README (Overview tab) |
|----------|------|------------------------|
| `10948768-5eb6-4d9e-a432-51796998697a` | `trip_agents` | [trip_agents/README.md](agents_store/10948768-5eb6-4d9e-a432-51796998697a/trip_agents/README.md) |
| `f1dc8d87-7fb3-40c7-b497-7c54ffd57f98` | `strategygpt_agents` | [strategygpt_agents/README.md](agents_store/f1dc8d87-7fb3-40c7-b497-7c54ffd57f98/strategygpt_agents/README.md) |

During local development, keep `teams/<team_name>/` and the matching `agents_store/<agent_id>/<team_name>/` copy in sync (see `.cursor/rules/sync-team-to-agents-store.mdc`).

## Run

From the repository root (with `.venv` activated):

```bash
python -m agent_platform.db.init_indexes   # first time only
python -m agent_platform.main
```

Open **http://localhost:8000**.

## MongoDB

Both the platform and agent teams use one local instance:

```
mongodb://127.0.0.1:55440/?directConnection=true
```

| Database | Contents |
|----------|----------|
| `agent_platform` | Agents, runs, schedules, `team_settings`, StrategyGPT collections |
| `trip_data` | Trip inventory, chat, reservations, vector indexes |

Set `MONGODB_URI` in the repo-root `.env`. Trip Agents also use `ATLAS_MONGODB_URI` (same host, `trip_data` database).

## Team-specific APIs

| Prefix | Team |
|--------|------|
| `/api/trip/{agent_id}` | Trip Agents — threads, search, reservations, seed, memory |
| `/api/strategygpt/{agent_id}` | StrategyGPT — leads, pipeline runs, voice outreach |

Team README files (shown in each agent's **Overview** tab) document business and technical details:

- Development source: `teams/trip_agents/README.md`, `teams/strategygpt_agents/README.md`
- Runtime copy: under `agents_store/<agent_id>/` (kept in sync during development)
