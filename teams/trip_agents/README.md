# Trip Agents

Multi-agent travel booking system powered by **LangGraph**, **MongoDB Atlas vector search**, and **Voyage AI** embeddings. Supports natural-language trip search, reservation management, and conversational interactions with short-term and long-term memory.

---

## Architecture Overview

```
                         ┌─────────────────────────────┐
                         │     FastAPI (trip.py)        │
                         │  Intent Detection & Routing  │
                         └──────────┬──────────────────┘
                                    │
                    ┌───────────────┼───────────────────┐
                    ▼               ▼                   ▼
              mode=chat        mode=reserve        mode=modify
              mode=cancel      mode=update
                    │               │                   │
                    ▼               ▼                   ▼
         ┌──────────────────┐  ┌──────────┐    ┌──────────────┐
         │   Orchestrator   │  │  Reserve  │    │    Modify    │
         │   (LangGraph)    │  │  Pipeline │    │  LLM-based   │
         │                  │  │           │    │  category    │
         │  parse_query     │  │  create_  │    │  detection   │
         │       │          │  │reservation│    │      ↓       │
         │  ┌────┼────┐     │  └──────────┘    │  Reuses sub- │
         │  ▼    ▼    ▼     │                  │  agent graph │
         │flight hotel car  │                  └──────────────┘
         │  └────┼────┘     │
         │       ▼          │
         │   aggregate      │
         └──────────────────┘
```

### Design Decisions

- **Deterministic search pipelines**: Sub-agents use fixed `embed → search → END` graphs rather than LLM-driven tool-calling loops. This is intentional — for a vector-search-only pipeline, deterministic execution is faster, more predictable, and easier to debug than adaptive agent behavior.
- **Conditional error edges**: Sub-agents short-circuit to `END` on embedding failure instead of running a guaranteed-to-fail search node.
- **Unified state**: All three sub-agents share a single `SearchAgentState` definition to eliminate code duplication.
- **Centralized prompts**: All LLM system prompts are stored as external text files in `shared/prompts/` and loaded via `shared/prompt_loader.py`, enabling prompt iteration without touching Python source.
- **Resilience**: LLM and Voyage API calls include automatic retry with exponential backoff (via `tenacity`). LLM clients are cached per provider+model to avoid redundant connection setup.
- **Non-blocking memory**: Long-term preference extraction runs in a background thread so it never delays the search response.

---

## Orchestrator Modes

The orchestrator (`orchestrator/main.py`) supports six modes, determined by the API route's intent detection layer:

| Mode | Trigger | Description |
|------|---------|-------------|
| `chat` | Any natural-language message | LLM classifies as search or conversation; runs search pipeline or returns a text reply |
| `search` | Stateless prompt via `run_config.json` | Direct search pipeline invocation |
| `reserve` | Internal `__RESERVE__` payload from UI | Creates a new reservation from selected options |
| `cancel` | Message contains reservation ID + cancel keywords | Deletes a reservation from Atlas |
| `modify` | Message contains reservation ID + change/swap/replace keywords | Targeted single-category search using the same sub-agent graphs as the main pipeline, with relaxed retry on empty results |
| `update` | Internal `__UPDATE__` payload from UI | Applies a selected replacement to an existing reservation |

### Intent Detection

The API route (`trip.py`) uses a deterministic routing layer before any LLM call:

1. **`__RESERVE__` / `__UPDATE__` prefixes** — Internal UI payloads, routed directly
2. **Reservation ID regex** (`TRIP-\d{8}-[A-Z0-9]{4}`) — Extracts the ID, then checks for cancel or modify keywords
3. **Default** — Falls through to `chat` mode, where the LLM handles intent classification

---

## LangGraph Pipelines

### Search Pipeline (parallel fan-out/fan-in)

```
START → parse_query → ┬─ flight_search ─┐
                       ├─ hotel_search  ─┤ → aggregate → END
                       └─ car_search   ──┘
```

- **`parse_query`** — Calls the LLM (using `shared/prompts/query_parser_system.txt`) with conversation history and long-term preferences to classify intent (`is_search: true/false`), extract structured filters, or generate a conversational reply
- **`flight_search` / `hotel_search` / `car_search`** — Run **in parallel** via LangGraph fan-out. Each invokes its sub-agent graph (embed → search)
- **`aggregate`** — Collects all results, generates an LLM-powered natural-language summary (using `shared/prompts/search_summary.txt`), saves to chat persistence, marks search-progress as done, and triggers background long-term memory extraction

State is defined in `orchestrator/state.py` as `TripSearchState` (TypedDict with parameterized generics).

### Reserve Pipeline

```
START → create_reservation → END
```

Single-node graph using `TripReserveState`. Accepts partial selections (any combination of flight, hotel, car). Generates a human-readable reservation ID (`TRIP-YYYYMMDD-XXXX`) and stores it in Atlas.

---

## Sub-Agents (Search Pipelines)

Each sub-agent is a self-contained LangGraph with conditional error handling:

```
embed_query ──(ok)──→ search_{category} → END
     │
     └──(error)──→ END
```

All three sub-agents share a single state definition (`shared/state.py:SearchAgentState`) re-exported under category-specific aliases for clarity.

| Agent | Directory | Atlas Collection | State Alias |
|-------|-----------|-----------------|-------------|
| Flight | `agent_flight/` | `trip_flights` | `FlightSearchState` |
| Hotel | `agent_hotel/` | `trip_hotels` | `HotelSearchState` |
| Car | `agent_car/` | `trip_cars` | `CarSearchState` |

### Node 1: `embed_query`
Calls the Voyage AI REST API (`voyage-3-lite` model, 512 dimensions) to convert the natural-language query into a dense vector embedding. On failure, sets `status: "error"` and the conditional edge routes directly to `END`.

### Node 2: `search_{category}`
Runs MongoDB Atlas `$vectorSearch` against the collection's `embedded_description` field with:
- **Cosine similarity** ranking
- **100 candidates**, returning **top 3**
- Optional **pre-filters** (exact match via `$eq`, minimum via `$gte`) for hard constraints

---

## Vector Search & Pre-Filtering

Each Atlas collection has a `vector_index` (type `vectorSearch`) with filterable fields:

| Collection | Filterable Fields |
|------------|-------------------|
| `trip_flights` | `origin_city`, `destination_city`, `travel_class` |
| `trip_hotels` | `city`, `stars` |
| `trip_cars` | `color`, `make`, `category`, `transmission`, `fuel_type`, `pickup_city` |

The LLM extracts filter values from the user's natural-language query. These are validated against allowed sets (e.g., `travel_class` must be one of `economy`, `premium economy`, `business`, `first`) before being applied as `$vectorSearch` pre-filters. This ensures exact-match constraints (e.g., "3-star hotel" never returns a 2-star).

Filter construction (`shared/atlas.py`):
- String fields → `{"field": {"$eq": value}}`
- `stars` field → `{"field": {"$gte": value}}`
- Multiple filters → `{"$and": [...]}`

---

## Prompt Management

All LLM system prompts are stored as external text files in `shared/prompts/` and loaded via `shared/prompt_loader.py`:

| Prompt File | Used By | Purpose |
|-------------|---------|---------|
| `query_parser_system.txt` | `shared/query_parser.py` | Intent classification + filter extraction |
| `memory_extraction.txt` | `shared/memory.py` | Long-term preference extraction from conversations |
| `intent_classifier.txt` | `shared/intent.py` | Search vs. cancel intent detection |
| `modify_parser.txt` | `orchestrator/main.py` | Category detection for reservation modifications |
| `search_summary.txt` | `orchestrator/graph.py` | Natural-language summary of search results |

The prompt loader supports `{{variable}}` placeholder substitution and caches loaded templates in memory.

---

## Resilience & Error Handling

### Retry Logic
All external API calls use `tenacity` for automatic retry with exponential backoff:
- **LLM calls** (`shared/llm.py`): 3 attempts, 1-10s backoff
- **Voyage AI calls** (`shared/voyage.py`): 3 attempts, 1-10s backoff, retries on `RequestException` and `Timeout`

### LLM Client Caching
`get_llm()` returns a cached singleton per provider+model combination, avoiding redundant client initialization and connection setup on every call.

### Timeouts
- LLM providers: 30s timeout (configured via `LLM_TIMEOUT`)
- Voyage AI: 60s timeout (configured via `VOYAGE_TIMEOUT`)

### Conditional Edges
Sub-agent graphs use conditional routing after the `embed_query` node — if embedding fails, the graph short-circuits to `END` with `status: "error"` instead of running a guaranteed-to-fail search.

### Relaxed Retry (Modify Flow)
When the modify search returns zero results with strict pre-filters (e.g., `make=BMW` + `pickup_city=Bucharest`), the system automatically retries with relaxed filters — removing location constraints (`pickup_city`, `city`, `origin_city`, `destination_city`) — to broaden the search before reporting no results. The chat message accurately reflects whether alternatives were found or not.

### Graceful Degradation
- If one sub-agent fails during parallel search, the others still complete
- LLM summary generation falls back to a template-based message on failure
- Memory extraction failures are logged but never block the response pipeline

---

## Memory Systems

### Short-Term Memory (Conversation Context)

- **Storage**: `trip_chatPersistence` collection in Atlas (`trip_data` database)
- **Scope**: Per-thread — each chat thread maintains its own message history
- **Window**: Last **8 messages** are passed to the LLM as `chat_history`
- **Persistence**: Survives application restarts (stored on Atlas)
- **Purpose**: Enables context-aware follow-up conversations, intent classification, and natural replies that reference previous results

**Flow**: On each message, the API fetches the thread's recent messages and passes them to the orchestrator. The query parser's LLM prompt includes this history for context-aware classification and response generation.

### Long-Term Memory (User Preferences)

- **Storage**: `trip_longMemory` collection in Atlas (`trip_data` database), keyed by `agent_id`
- **Scope**: Cross-thread, cross-session — preferences persist across all conversations
- **Capacity**: Capped at **30 preferences** (oldest pruned when exceeded)
- **Extraction**: Runs in a **background thread** after each interaction — never blocks the search response
- **Purpose**: Personalizes recommendations without the user repeating themselves

**Learning (extraction)**: After every orchestrator interaction, a background thread calls the LLM (using `shared/prompts/memory_extraction.txt`) to analyze the conversation and extract new travel preferences. New facts are deduplicated (case-insensitive) against existing ones before saving.

**Injection (recall)**: At the start of every query, stored preferences are loaded from Atlas and appended to the LLM system prompt. The LLM considers them when classifying intent, extracting filters, and generating search summaries.

**Document structure**:
```json
{
  "_id": "<agent_id>",
  "preferences": [
    { "fact": "Prefers 5-star hotels", "category": "hotel", "learned_at": "..." },
    { "fact": "Avoids diesel cars", "category": "car", "learned_at": "..." }
  ],
  "updated_at": "..."
}
```

**UI**: The "What I remember about you" collapsible section on the Trip Planner tab displays stored preferences with a "Clear all memories" button.

---

## MongoDB Atlas Collections

All trip domain data lives on Atlas in the `trip_data` database:

| Collection | Purpose | Key Fields |
|------------|---------|------------|
| `trip_flights` | 1,000 seed flight documents | `airline`, `flight_number`, `origin_city`, `destination_city`, `travel_class`, `price_eur`, `text_description`, `embedded_description` (512-dim vector) |
| `trip_hotels` | 1,000 seed hotel documents | `name`, `city`, `stars`, `amenities`, `price_per_night_eur`, `neighborhood`, `text_description`, `embedded_description` |
| `trip_cars` | 1,000 seed car rental documents | `make`, `model`, `color`, `category`, `transmission`, `fuel_type`, `price_per_day_eur`, `pickup_city`, `text_description`, `embedded_description` |
| `trip_reservations` | Confirmed bookings | `_id` (human-readable `TRIP-YYYYMMDD-XXXX`), `flight`, `hotel`, `car`, `trip_dates`, `total_cost_eur`, `status`, `agent_id` |
| `trip_chatPersistence` | Chat thread history | `agent_id`, `title`, `messages[]` (role, content, timestamp, search_results, reservation, cancellation, modify_results), `created_at`, `updated_at` |
| `trip_longMemory` | Learned user preferences | `_id` (agent_id), `preferences[]` (fact, category, learned_at), `updated_at` |
| `trip_search_progress` | Ephemeral — tracks partial search results for progressive UI streaming | `_id` (thread_id), `flights`, `hotels`, `cars`, `done`, `started_at` |
| `trip_seed_status` | Tracks data seeding progress and status | `_id` (agent_id), `status`, `detail`, `error`, `updated_at` |

---

## LLM Integration

The system supports multiple LLM providers via `shared/llm.py`, with cached singleton clients and automatic retry:

| Provider | Models |
|----------|--------|
| **Anthropic Claude** | `claude-sonnet-4-20250514`, `claude-3-5-haiku-20241022` |
| **Google Gemini** | `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.0-flash` |
| **OpenAI** | `gpt-4o`, `gpt-4o-mini`, `o3-mini` |
| **DeepSeek** | `deepseek-chat`, `deepseek-reasoner` |
| **Groq** | `llama-3.3-70b-versatile`, `llama-3.1-8b-instant` |

The active provider/model is configured in the platform's Settings tab and stored in `team_settings`. The LLM is used for:

1. **Intent classification** — Search vs. conversational vs. follow-up
2. **Filter extraction** — Structured constraints from natural language
3. **Conversational replies** — Context-aware responses for non-search messages
4. **Search summaries** — Natural-language overviews of search results
5. **Preference extraction** — Long-term memory learning (background)
6. **Modify category detection** — Determining which reservation component to replace

---

## Custom UI Tabs

### Trip Planner (`ui/tabs/trip_planner.html`)

Split-panel layout:

- **Left panel**: Search results with selectable cards (click to select, click again to deselect), collapsible detail descriptions, progressive streaming as each sub-agent completes, and reserve/update buttons
- **Right panel**: Chat interface with thread management (max 5 threads), suggested prompts (generated from actual MongoDB data), LLM model badge, and the "What I remember about you" memory section

### Reservations (`ui/tabs/trip_reservations.html`)

Displays confirmed reservations with full flight/hotel/car details, human-readable reservation IDs, total cost, and a delete button.

---

## Seed Data

Sample data (1,000 documents per collection) is generated via `seed_data.py` or the **Load Sample Data** button on the Settings tab. Each document includes:

- Realistic attributes (airlines, hotel chains, car brands, cities, prices)
- Rich narrative `text_description` fields designed for semantic search quality
- 512-dimensional Voyage AI embeddings in `embedded_description`
- Atlas `vectorSearch` indexes with filterable fields

The seeding process drops existing collections, re-inserts fresh data, computes embeddings via the Voyage AI API, and creates new vector search indexes.

---

## API Endpoints

All endpoints are prefixed with `/api/trip/{agent_id}`:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/threads` | List chat threads |
| `POST` | `/threads` | Create a new thread |
| `GET` | `/threads/{id}` | Get thread with messages |
| `DELETE` | `/threads/{id}` | Delete a thread |
| `POST` | `/threads/{id}/messages` | Send message (routes to appropriate mode) |
| `GET` | `/threads/{id}/search-progress` | Poll partial search results |
| `GET` | `/suggestions` | Get 3 suggested prompts from live data |
| `GET` | `/reservations` | List confirmed reservations |
| `DELETE` | `/reservations/{id}` | Delete a reservation |
| `GET` | `/memory` | Get stored user preferences |
| `DELETE` | `/memory` | Clear all preferences |
| `GET` | `/seed/status` | Check if data is seeded |
| `POST` | `/seed` | Trigger data seeding |
| `GET` | `/seed/progress` | Poll seeding progress |

---

## Setup

1. Set **VOYAGE_AI_API_KEY** and **ATLAS_MONGODB_URI** in the platform Settings tab
2. Click **Load Sample Data** on the Settings tab (or run `python seed_data.py` manually)
3. Configure your preferred LLM provider and model in Settings
4. Navigate to the **Trip Planner** tab and start chatting

## Requirements

See `requirements.txt`. Key dependencies:

- **LangGraph** — Multi-agent orchestration with parallel execution
- **PyMongo** — MongoDB Atlas driver
- **Voyage AI** — Semantic embeddings (`voyage-3-lite`, 512 dimensions)
- **Tenacity** — Retry with exponential backoff for external API calls
- **Anthropic / Google GenAI / OpenAI / Groq** — LLM providers
- **Certifi** — SSL certificate handling for Atlas connections

## File Structure

```
trip_agents/
├── orchestrator/
│   ├── main.py          # Entry point — mode dispatch
│   ├── graph.py          # LangGraph pipelines (search + reserve)
│   └── state.py          # TypedDict state definitions (TripSearchState, TripReserveState)
├── agent_flight/
│   ├── agent.py          # Flight sub-agent graph (with conditional error edge)
│   ├── state.py          # Re-exports SearchAgentState as FlightSearchState
│   ├── main.py           # Standalone demo entry point
│   ├── nodes/
│   │   ├── embed_query.py
│   │   └── search_flights.py
│   └── memory/
│       └── store.py      # Recent-search data accessor
├── agent_hotel/          # (same structure as agent_flight)
├── agent_car/            # (same structure as agent_flight)
├── shared/
│   ├── atlas.py          # Atlas client, vector_search, collection accessors
│   ├── mongo.py          # Local MongoDB client, team_settings, LLM/key config
│   ├── llm.py            # Multi-provider LLM wrapper (cached, retry, timeouts)
│   ├── voyage.py         # Voyage AI embedding client (retry-enabled)
│   ├── query_parser.py   # LLM-based intent + filter extraction
│   ├── memory.py         # Long-term preference extraction and injection
│   ├── intent.py         # Search vs. cancel intent classifier
│   ├── state.py          # Shared SearchAgentState for all sub-agents
│   ├── prompt_loader.py  # Centralized prompt template loader with caching
│   ├── prompts/          # External LLM prompt templates
│   │   ├── query_parser_system.txt
│   │   ├── memory_extraction.txt
│   │   ├── intent_classifier.txt
│   │   ├── modify_parser.txt
│   │   └── search_summary.txt
│   ├── config.py         # Environment variables and constants
│   ├── logger.py         # Logging configuration
│   └── utils.py          # Argument loading utilities
├── ui/
│   ├── tabs.json         # Tab definitions
│   └── tabs/
│       ├── trip_planner.html       # Chat + search UI
│       └── trip_reservations.html  # Reservations UI
├── tests/
│   └── test_pipeline.py  # Import, state, and utility smoke tests
├── data/                 # Input/output data placeholders
├── checkpoints/          # LangGraph checkpoint storage
├── seed_data.py          # Atlas data seeding script
├── build_zip.py          # Package builder for deployment
├── run_config.json       # Stateless run configuration
├── requirements.txt
└── README.md
```
