# Trip Agents

An AI-powered travel assistant that helps people search for flights, hotels, and rental cars in plain language, compare options, and manage bookings — all through a conversational interface.

---

## For Business Stakeholders

### What this product does

Trip Agents is a **virtual travel planner** embedded in the AI Agent Platform. Instead of filling out separate forms for flights, hotels, and cars, users describe what they want in natural language — for example:

> *"I'm flying from Doha to Athens in early March. I need a quiet hotel near the river with a bar, and a manual Kia for getting around."*

The assistant understands the request, searches a catalog of travel options, presents the best matches, and can help the user **confirm a reservation**, **change** an existing booking, or **cancel** it — all within the same chat experience.

### Who it is for

- **Travelers and planners** who want a faster, conversational way to explore trip options
- **Product and operations teams** evaluating how multi-agent AI can automate search-and-book workflows
- **Demo and pilot use cases** where realistic sample inventory (flights, hotels, cars) is sufficient — this is not connected to live GDS or OTA APIs

### What users can do today

| Capability | User experience |
|------------|-----------------|
| **Search trips** | Ask for flights, hotels, cars, or any combination. Results appear on the left; the assistant explains and recommends a bundle on the right. |
| **Get inspired** | Click a suggested prompt (built from real sample data) or type freely. Up to five chat threads are supported. |
| **Review and select** | Browse ranked options, expand details, select cards manually, or accept the assistant's proposed package. |
| **Book** | Confirm a reservation; the system assigns a readable ID (`TRIP-20260522-A1B2`) and stores it. |
| **Modify** | Reference a reservation ID in chat and ask to change the flight, hotel, or car; pick a replacement and apply it. |
| **Cancel** | Ask to cancel a reservation by ID, or delete it from the Reservations tab. |
| **Personalization** | The assistant learns preferences over time (e.g. "prefers business class", "avoids diesel cars") and applies them in future searches. Users can view and clear stored memories. |

### How a typical journey works

```
1. User opens Trip Planner
2. User describes a trip (or clicks a suggested prompt)
3. Assistant searches flights / hotels / cars as requested
4. Results stream into the left panel; assistant summarizes and may propose a bundle
5. User confirms selections → reservation is created
6. Later: user can modify or cancel via chat or the Reservations tab
```

### What makes it different from a simple chatbot

- **Structured search, not hallucination** — Options come from a real MongoDB catalog (`trip_data` on `127.0.0.1:55440`) with semantic (meaning-based) search, not invented listings.
- **Selective planning** — The AI decides *which* categories to search (flights only, hotel + car, full trip, etc.) instead of always running everything.
- **Memory** — Short-term context within a chat thread plus long-term preferences across sessions.
- **Human in the loop** — Nothing is booked without explicit user confirmation.

### Setup requirements (non-technical summary)

Before the assistant can search, an administrator must:

1. Ensure **MongoDB** is running at `mongodb://127.0.0.1:55440/?directConnection=true` (platform and trip data share this instance)
2. Add a **Voyage AI** key (powers semantic search quality)
3. Choose an **LLM provider** (e.g. Claude, Gemini, OpenAI) in the agent Settings tab
4. Load **sample data** once via Settings → "Load Sample Data" (3,000 documents: flights, hotels, cars)

### Limitations to be aware of

- Inventory is **synthetic sample data**, not live airline or hotel feeds
- LLM usage depends on provider quotas and API keys; if the model is unavailable, search cannot start
- Reservations default traveler name to **Guest** unless `traveler_name` is passed in the reserve payload
- Maximum **five** concurrent chat threads per agent

---

## For Developers & Architects

### System context

Trip Agents runs as an **uploaded agent team** on the AI Agent Platform (repository root `README.md`). Development source lives under `teams/trip_agents/`; at runtime the platform executes from `agent_platform/agents_store/<agent_id>/trip_agents/` (current agent ID: `10948768-5eb6-4d9e-a432-51796998697a`).

When you edit files under `teams/trip_agents/`, mirror the same change under the matching `agents_store` copy so the running platform picks it up without re-uploading the zip. See `.cursor/rules/sync-team-to-agents-store.mdc` in the repository.

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser UI (trip_planner.html, trip_reservations.html)         │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST
┌────────────────────────────▼────────────────────────────────────┐
│  agent_platform/api/routes/trip.py                              │
│  Threads · Messages · Suggestions · Seed · Memory · Reservations│
└────────────────────────────┬────────────────────────────────────┘
                             │ subprocess + AGENT_ARGS
┌────────────────────────────▼────────────────────────────────────┐
│  orchestrator/main.py  →  LangGraph (plan-and-execute)            │
│       ↓                                                         │
│  agent_flight · agent_hotel · agent_car  (vector search tools)  │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┴───────────────────┐
         ▼                                       ▼
  MongoDB @ 127.0.0.1:55440              MongoDB @ 127.0.0.1:55440
  database: agent_platform               database: trip_data
  team_settings, platform metadata       inventory, chat, bookings
```

Both connections use the same MongoDB instance (`mongodb://127.0.0.1:55440/?directConnection=true`); only the database name differs.

### Architecture: plan-and-execute orchestrator

The core pattern is **Plan-and-Execute** (not ReAct tool-calling). The LLM returns a structured JSON plan; Python executes tools deterministically; the LLM synthesizes results into a user-facing reply and optional **proposed bundle**.

```
START → plan → execute_tools → (replan loop, max 2) → synthesize → persist → END
         │            │
         └─ chat ─────┴─→ persist → END  (no search)
```

| Node | Responsibility |
|------|----------------|
| `plan` | LLM reads conversation + long-term prefs; returns `intent` (`chat` / `search` / `replan`) and optional `tool_calls` |
| `execute_tools` | Runs planned tools (independent searches in parallel); publishes partial results to `trip_search_progress` for UI streaming |
| `replan_bump` | Increments retry counter when **all** invoked search tools return zero results |
| `synthesize` | LLM picks best options and builds `proposed_bundle`; heuristic fallback if LLM fails |
| `persist` | Writes assistant message to `trip_data`; triggers background preference extraction |

**Design rationale:** JSON planning avoids paid provider-native tool-calling, keeps search execution predictable, and lets the LLM focus on *what* to search rather than *how* vector search works.

### Orchestrator modes

Determined by `orchestrator/main.py` from `AGENT_ARGS.mode`:

| Mode | Trigger | Behavior |
|------|---------|----------|
| `chat` | Default user message via API | Full plan-and-execute graph with thread persistence |
| `search` | Stateless run via `run_config.json` | Same graph, no thread UI context |
| `reserve` | UI sends `__RESERVE__{json}` | Single-node reserve graph → `trip_reservations` |
| `cancel` | Message with reservation ID + cancel keywords | Direct delete + chat confirmation |
| `modify` | Message with reservation ID + change keywords | Plan-and-execute in modify mode (single category) |
| `update` | UI sends `__UPDATE__{json}` | Patches reservation document in `trip_data` (category whitelisted) |

**API intent routing** (`trip.py` `_detect_message_mode`) runs *before* the agent subprocess:

1. Internal prefixes `__RESERVE__` / `__UPDATE__`
2. Regex `TRIP-\d{8}-[A-Z0-9]{4}` + keyword heuristics for cancel/modify
3. Otherwise → `chat`

### Sub-agents (search tools)

Each category is a small LangGraph (shared embed + search nodes in `shared/nodes/`) invoked as a tool from `orchestrator/tools.py`. Compiled graphs and query embeddings are cached per process.

```
embed_query ──(ok)──→ search_{flights|hotels|cars} → END
     └──(error)──→ END
```

| Agent | Directory | `trip_data` collection | State alias |
|-------|-----------|------------------------|-------------|
| Flight | `agent_flight/` | `trip_flights` | `FlightSearchState` |
| Hotel | `agent_hotel/` | `trip_hotels` | `HotelSearchState` |
| Car | `agent_car/` | `trip_cars` | `CarSearchState` |

All share `SearchAgentState` in `shared/state.py`.

**Search pipeline:**

1. **Embed** — Voyage AI `voyage-3-lite`, 512 dimensions (`shared/voyage.py`)
2. **Vector search** — `$vectorSearch` on `embedded_description`, cosine similarity, 100 candidates → top 3 (`shared/atlas.py`)
3. **Pre-filters** — Exact match on structured fields extracted from the plan (e.g. `destination_city`, `stars`)

| Collection | Filterable fields |
|------------|-------------------|
| `trip_flights` | `origin_city`, `destination_city`, `travel_class` |
| `trip_hotels` | `city`, `stars` (`$gte`) |
| `trip_cars` | `pickup_city`, `make`, `category`, `color`, `transmission`, `fuel_type` |

**Available tools** (defined in plan prompt):

- `search_flights`, `search_hotels`, `search_cars`
- `get_user_preferences`, `get_reservation`

The plan prompt (`trip_planner_plan.txt`) instructs the LLM to call **only** the categories the user explicitly requested.

### Data layer: two databases, one MongoDB instance

All data lives on **`mongodb://127.0.0.1:55440/?directConnection=true`**.

| Store | Connection variable | Database | Contents |
|-------|---------------------|----------|----------|
| **Platform** | `MONGODB_URI` | `agent_platform` | `team_settings` (LLM provider, API keys, Voyage key) |
| **Trip domain** | `ATLAS_MONGODB_URI` | `trip_data` | Flights, hotels, cars, chat, reservations, vector indexes |

Both variables default to `mongodb://127.0.0.1:55440/?directConnection=true`. Set them in repo-root `.env` and in the agent Settings tab.

#### Trip domain collections (`trip_data` on `127.0.0.1:55440`)

| Collection | Purpose |
|------------|---------|
| `trip_flights` | Flight inventory (1,000 seed docs) + vector index |
| `trip_hotels` | Hotel inventory (1,000 seed docs) + vector index |
| `trip_cars` | Car rental inventory (1,000 seed docs) + vector index |
| `trip_reservations` | Confirmed bookings scoped by `agent_id` |
| `trip_chatPersistence` | Chat threads and message history |
| `trip_longMemory` | Long-term user preferences (`_id` = agent_id, max 30 facts) |
| `trip_search_progress` | Ephemeral partial results for UI polling (`_id` = thread_id) |
| `trip_seed_status` | Background seed job status (`_id` = agent_id) |

Seed via **Settings → Load Sample Data** (`POST /api/trip/{agent_id}/seed`) or CLI `python seed_data.py`. Seeded when total docs ≥ 2,500.

### Memory

| Type | Storage | Scope | Mechanism |
|------|---------|-------|-----------|
| **Short-term** | `trip_chatPersistence` | Per thread | Last 8 messages passed as `chat_history` to plan/synthesize |
| **Long-term** | `trip_longMemory` | Per agent, cross-thread | Background LLM extraction after each turn (`memory_extraction.txt`); injected into plan prompt |

### LLM integration

`shared/llm.py` supports **Gemini, Claude, OpenAI, DeepSeek, Groq** — configured in the platform Settings tab (`team_settings`). Clients are cached per provider/model with tenacity retry (3×, exponential backoff, 30s timeout).

Active prompts:

| File | Used by |
|------|---------|
| `trip_planner_plan.txt` | `plan` node |
| `trip_planner_synthesize.txt` | `synthesize` node |
| `memory_extraction.txt` | Background preference learning |

### Suggested prompts API

`GET /api/trip/{agent_id}/suggestions` builds three example prompts from **coherent samples** in `trip_data`: a flight's `destination_city` is joined to a hotel in the same `city` and a car with matching `pickup_city` (aggregation with `$lookup`). Falls back to static prompts if MongoDB is unavailable.

### API endpoints

Prefix: `/api/trip/{agent_id}` — implemented in `agent_platform/api/routes/trip.py`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/threads` | List chat threads (max 5) |
| `POST` | `/threads` | Create thread |
| `GET` | `/threads/{id}` | Get thread with messages |
| `DELETE` | `/threads/{id}` | Delete thread |
| `POST` | `/threads/{id}/messages` | Send message → spawns agent run |
| `GET` | `/threads/{id}/search-progress` | Poll partial search results |
| `GET` | `/suggestions` | Three sample prompts from live data |
| `GET` | `/reservations` | List reservations |
| `DELETE` | `/reservations/{id}` | Delete reservation |
| `GET` | `/memory` | Get stored preferences |
| `DELETE` | `/memory` | Clear preferences |
| `GET` | `/seed/status` | Check if sample data exists |
| `POST` | `/seed` | Start background seed |
| `GET` | `/seed/progress` | Poll seed progress |

Responses: `{ "success": bool, "data": ..., "error": string | null }`.

### Custom UI tabs

`ui/tabs.json`:

```json
{
  "tabs": [
    { "id": "trip_planner", "label": "Trip Planner" },
    { "id": "trip_reservations", "label": "Reservations" }
  ]
}
```

- **Trip Planner** — Split panel: search results (left), chat + suggestions + memory (right)
- **Reservations** — List and delete confirmed bookings

### Configuration

**Per-agent (Settings tab → stored in local `team_settings`):**

| Key | Purpose |
|-----|---------|
| `llm_provider`, `llm_model`, `api_keys` | LLM selection |
| `ATLAS_MONGODB_URI` | Trip domain connection (`trip_data` on `127.0.0.1:55440`) |
| `VOYAGE_AI_API_KEY` | Embeddings for search and seeding |

**Environment fallbacks** (`shared/config.py`): `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `GROQ_API_KEY`, `MONGODB_URI`, `ATLAS_MONGODB_URI`, `VOYAGE_AI_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL`

**Project `.env` (local dev & Cursor MCP):** Copy `.env.example` to `.env` at the repository root. Both `MONGODB_URI` and `ATLAS_MONGODB_URI` should be `mongodb://127.0.0.1:55440/?directConnection=true`. Also set `VOYAGE_AI_API_KEY` for MCP and CLI seeding. The platform UI Settings tab writes the same keys into `team_settings` for runtime agent subprocesses. To sync `ATLAS_MONGODB_URI` into Settings after changing `.env`, run `scripts/update-atlas-uri.sh`.

**Cursor MCP:** One MCP server — **`MongoDB-Atlas-Local`** — loads the connection string from `.env` via `.cursor/run-mongodb-mcp.sh`. Never put credentials in `.cursor/mcp.json`. Uses `ATLAS_MONGODB_URI` (fallback: `MONGODB_URI`), defaulting to `mongodb://127.0.0.1:55440/?directConnection=true`. You can query both `agent_platform` and `trip_data` from this single connection.

**Runtime (set by platform executor):** `AGENT_ID`, `AGENT_ARGS` (JSON with `mode`, `thread_id`, `message`, `chat_history`, etc.)

### Resilience & error handling

- LLM and Voyage calls retry transient failures with exponential backoff (`tenacity`); missing API keys fail fast
- Sub-agents short-circuit on embedding failure (conditional edge to `END`)
- Empty search results trigger replan (max 2) only when **all** planned searches return zero rows
- Synthesize falls back to heuristic bundle if LLM fails (uses trip dates for cost when available)
- Plan node returns a user-friendly error if the LLM is unavailable (e.g. API quota exceeded)
- Memory extraction runs in a background thread — never blocks the response
- Reservations are scoped by `agent_id`; update mode whitelists `flight` / `hotel` / `car` categories

### Packaging & deployment

```bash
cd teams/trip_agents
python3 build_zip.py
# → trip_agents.zip ready for upload to the platform
```

`run_config.json` defines a stateless **Run** modal with a single `prompt` textarea for `mode=search` executions outside the Trip Planner UI.

### File structure

```
trip_agents/
├── orchestrator/
│   ├── main.py           # Mode dispatch entry point
│   ├── graph.py          # Plan-and-execute + reserve LangGraphs
│   ├── state.py          # TripAgentState, TripReserveState
│   └── tools.py          # Tool registry, search progress publishing
├── agent_flight/         # Flight search sub-agent (agent.py + shared nodes)
├── agent_hotel/          # Hotel search sub-agent
├── agent_car/            # Car search sub-agent
├── shared/
│   ├── atlas.py          # Atlas client, vector_search, collection accessors
│   ├── mongo.py          # Local MongoDB, team_settings, key loaders
│   ├── llm.py            # Multi-provider LLM (cached, retry)
│   ├── voyage.py         # Voyage AI embeddings
│   ├── memory.py         # Long-term preference extract/inject
│   ├── json_utils.py     # Brace-aware JSON extraction from LLM output
│   ├── filters.py        # Search filter validation for tool plans
│   ├── nodes/            # Shared embed + vector-search LangGraph nodes
│   ├── search_graph.py   # Shared embed → search graph builder
│   ├── state.py          # Shared SearchAgentState
│   ├── prompt_loader.py  # Prompt template loader
│   ├── prompts/          # trip_planner_plan, trip_planner_synthesize, memory_extraction
│   ├── config.py         # Environment variables and constants
│   ├── logger.py
│   └── utils.py
├── ui/
│   ├── tabs.json
│   └── tabs/
│       ├── trip_planner.html
│       └── trip_reservations.html
├── tests/
│   └── test_pipeline.py
├── seed_data.py          # CLI Atlas seeding script
├── build_zip.py
├── run_config.json
├── requirements.txt
└── README.md
```

### Key dependencies

- **LangGraph** — Orchestrator and sub-agent graphs (no LangChain dependency)
- **PyMongo** — MongoDB driver for local `127.0.0.1:55440` and Atlas-compatible `$vectorSearch`
- **Voyage AI** — Semantic embeddings (`voyage-3-lite`, 512-dim)
- **Tenacity** — Retry with exponential backoff
- **Anthropic / Google GenAI / OpenAI / Groq** — LLM provider SDKs
- **Certifi** — TLS when using cloud MongoDB URIs

### Quick start (developers)

```bash
# 0. Platform setup (repository root README.md and .env.example):
cp .env.example .env
# Defaults in .env.example:
#   MONGODB_URI=mongodb://127.0.0.1:55440/?directConnection=true
#   ATLAS_MONGODB_URI=mongodb://127.0.0.1:55440/?directConnection=true
# Also set VOYAGE_AI_API_KEY and LLM provider keys.

# 1. Configure keys in the platform Settings tab for the trip agent
#    (ATLAS_MONGODB_URI, VOYAGE_AI_API_KEY, LLM provider + API key).
#    ATLAS_MONGODB_URI should be mongodb://127.0.0.1:55440/?directConnection=true

# 2. Load sample data (Settings → Load Sample Data, or CLI):
export ATLAS_MONGODB_URI="mongodb://127.0.0.1:55440/?directConnection=true"
export VOYAGE_AI_API_KEY="..."
python seed_data.py

# 3. Open Agent Detail → Dashboard → Trip Planner and chat

# 4. After editing source under teams/trip_agents/, sync to agents_store
#    (or re-run build_zip.py and re-upload)

# 5. Package for upload:
python build_zip.py
```

### Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| "I'm having trouble processing that right now" | LLM API failure (quota, rate limit, invalid key). Check agent run logs under `agents_store/<id>/logs/`. Try another provider in Settings. |
| Empty search results | Sample data not seeded, or vector indexes still building (~30s after seed) |
| Suggestions show mismatched cities | Should not occur after coherent-trip sampling; verify `/suggestions` API |
| Auth / connection errors | Missing or wrong `ATLAS_MONGODB_URI` or `VOYAGE_AI_API_KEY` in Settings or `.env`; URI should be `mongodb://127.0.0.1:55440/?directConnection=true` |
| MCP cannot connect | `MONGODB_URI` / `ATLAS_MONGODB_URI` not set in repo-root `.env`; restart Cursor after updating |
| MongoDB connection refused | MongoDB not running on `127.0.0.1:55440` |
