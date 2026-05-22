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

- **Structured search, not hallucination** — Options come from a real MongoDB Atlas catalog with semantic (meaning-based) search, not invented listings.
- **Selective planning** — The AI decides *which* categories to search (flights only, hotel + car, full trip, etc.) instead of always running everything.
- **Memory** — Short-term context within a chat thread plus long-term preferences across sessions.
- **Human in the loop** — Nothing is booked without explicit user confirmation.

### Setup requirements (non-technical summary)

Before the assistant can search, an administrator must:

1. Connect **MongoDB Atlas** (where trip inventory and conversations live)
2. Add a **Voyage AI** key (powers semantic search quality)
3. Choose an **LLM provider** (e.g. Claude, Gemini, OpenAI) in the agent Settings tab
4. Load **sample data** once via Settings → "Load Sample Data" (3,000 documents: flights, hotels, cars)

### Limitations to be aware of

- Inventory is **synthetic sample data**, not live airline or hotel feeds
- LLM usage depends on provider quotas and API keys; if the model is unavailable, search cannot start
- Reservations use a placeholder traveler name in the current implementation
- Maximum **five** concurrent chat threads per agent

---

## For Developers & Architects

### System context

Trip Agents runs as an **uploaded agent team** on the AI Agent Platform. Development source lives under `teams/trip_agents/`; at runtime the platform executes from `agent_platform/agents_store/<agent_id>/trip_agents/`.

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
  Local MongoDB (agent_platform)          Atlas MongoDB (trip_data)
  team_settings, platform metadata        inventory, chat, bookings
```

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
| `execute_tools` | Runs planned tools sequentially; publishes partial results to `trip_search_progress` for UI streaming |
| `replan_bump` | Increments retry counter when a search tool returns zero results |
| `synthesize` | LLM picks best options and builds `proposed_bundle`; heuristic fallback if LLM fails |
| `persist` | Writes assistant message to Atlas; triggers background preference extraction |

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
| `update` | UI sends `__UPDATE__{json}` | Patches reservation document in Atlas |

**API intent routing** (`trip.py` `_detect_message_mode`) runs *before* the agent subprocess:

1. Internal prefixes `__RESERVE__` / `__UPDATE__`
2. Regex `TRIP-\d{8}-[A-Z0-9]{4}` + keyword heuristics for cancel/modify
3. Otherwise → `chat`

### Sub-agents (search tools)

Each category is a small LangGraph invoked as a tool from `orchestrator/tools.py`:

```
embed_query ──(ok)──→ search_{flights|hotels|cars} → END
     └──(error)──→ END
```

| Agent | Directory | Atlas collection | State alias |
|-------|-----------|------------------|-------------|
| Flight | `agent_flight/` | `trip_flights` | `FlightSearchState` |
| Hotel | `agent_hotel/` | `trip_hotels` | `HotelSearchState` |
| Car | `agent_car/` | `trip_cars` | `CarSearchState` |

All share `SearchAgentState` in `shared/state.py`.

**Search pipeline:**

1. **Embed** — Voyage AI `voyage-3-lite`, 512 dimensions (`shared/voyage.py`)
2. **Vector search** — Atlas `$vectorSearch` on `embedded_description`, cosine similarity, 100 candidates → top 3 (`shared/atlas.py`)
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

### Data layer: two MongoDB databases

| Store | Connection | Database | Contents |
|-------|------------|----------|----------|
| **Local** | `MONGODB_URI` | `agent_platform` | `team_settings` (LLM provider, API keys, Atlas URI, Voyage key) |
| **Atlas** | `ATLAS_MONGODB_URI` | `trip_data` | All trip domain data |

#### Atlas collections (`trip_data`)

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

Loaded via `shared/prompt_loader.py` with optional `{{variable}}` substitution.

### Suggested prompts API

`GET /api/trip/{agent_id}/suggestions` builds three example prompts from **coherent Atlas samples**: a flight's `destination_city` is joined to a hotel in the same `city` and a car with matching `pickup_city` (aggregation with `$lookup`). Falls back to static prompts if Atlas is unavailable.

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
| `ATLAS_MONGODB_URI` | Atlas connection for all trip data |
| `VOYAGE_AI_API_KEY` | Embeddings for search and seeding |

**Environment fallbacks** (`shared/config.py`): `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `GROQ_API_KEY`, `MONGODB_URI`, `ATLAS_MONGODB_URI`, `VOYAGE_AI_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL`

**Runtime (set by platform executor):** `AGENT_ID`, `AGENT_ARGS` (JSON with `mode`, `thread_id`, `message`, `chat_history`, etc.)

### Resilience & error handling

- LLM and Voyage calls retry with exponential backoff (`tenacity`)
- Sub-agents short-circuit on embedding failure (conditional edge to `END`)
- Empty search results trigger replan (max 2) with relaxed filters
- Synthesize falls back to heuristic bundle if LLM fails
- Plan node returns a user-friendly error if the LLM is unavailable (e.g. API quota exceeded)
- Memory extraction runs in a background thread — never blocks the response

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
├── agent_flight/         # Flight search sub-agent
├── agent_hotel/          # Hotel search sub-agent
├── agent_car/            # Car search sub-agent
├── shared/
│   ├── atlas.py          # Atlas client, vector_search, collection accessors
│   ├── mongo.py          # Local MongoDB, team_settings, key loaders
│   ├── llm.py            # Multi-provider LLM (cached, retry)
│   ├── voyage.py         # Voyage AI embeddings
│   ├── memory.py         # Long-term preference extract/inject
│   ├── query_parser.py   # Filter validation helpers for tools
│   ├── state.py          # Shared SearchAgentState
│   ├── prompt_loader.py  # Prompt template loader
│   ├── prompts/          # External LLM prompt files
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

- **LangGraph** — Orchestrator and sub-agent graphs
- **PyMongo** — MongoDB Atlas driver
- **Voyage AI** — Semantic embeddings (`voyage-3-lite`, 512-dim)
- **Tenacity** — Retry with exponential backoff
- **Anthropic / Google GenAI / OpenAI / Groq** — LLM provider SDKs
- **Certifi** — TLS for Atlas connections

### Quick start (developers)

```bash
# 1. Configure keys in the platform Settings tab for the trip agent:
#    ATLAS_MONGODB_URI, VOYAGE_AI_API_KEY, LLM provider + API key

# 2. Load sample data (Settings → Load Sample Data, or CLI):
export ATLAS_MONGODB_URI="mongodb+srv://..."
export VOYAGE_AI_API_KEY="..."
python seed_data.py

# 3. Open Agent Detail → Dashboard → Trip Planner and chat

# 4. Package for upload:
python build_zip.py
```

### Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| "I'm having trouble processing that right now" | LLM API failure (quota, rate limit, invalid key). Check agent run logs under `agents_store/<id>/logs/`. Try another provider in Settings. |
| Empty search results | Sample data not seeded, or vector indexes still building (~30s after seed) |
| Suggestions show mismatched cities | Should not occur after coherent-trip sampling; verify `/suggestions` API |
| Auth / connection errors | Missing or wrong `ATLAS_MONGODB_URI` or `VOYAGE_AI_API_KEY` in Settings |
