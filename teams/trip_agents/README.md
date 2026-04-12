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
         │   (LangGraph)    │  │  Pipeline │    │  (Targeted   │
         │                  │  │           │    │   Search)    │
         │  parse_query     │  │  create_  │    │              │
         │       │          │  │reservation│    │  LLM → category
         │  ┌────┼────┐     │  └──────────┘    │  detection → │
         │  ▼    ▼    ▼     │                  │  single-agent│
         │ ✈️   🏨   🚗    │                  │  search      │
         │flight hotel car  │                  └──────────────┘
         │  └────┼────┘     │
         │       ▼          │
         │   aggregate      │
         └──────────────────┘
```

---

## Orchestrator Modes

The orchestrator (`orchestrator/main.py`) supports six modes, determined by the API route's intent detection layer:

| Mode | Trigger | Description |
|------|---------|-------------|
| `chat` | Any natural-language message | LLM classifies as search or conversation; runs search pipeline or returns a text reply |
| `search` | Stateless prompt via `run_config.json` | Direct search pipeline invocation |
| `reserve` | Internal `__RESERVE__` payload from UI | Creates a new reservation from selected options |
| `cancel` | Message contains reservation ID + cancel keywords | Deletes a reservation from Atlas |
| `modify` | Message contains reservation ID + change/swap/replace keywords | Targeted single-category search to find replacement options |
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

- **`parse_query`** — Calls the LLM (`shared/query_parser.py`) with conversation history and long-term preferences to classify intent (`is_search: true/false`), extract structured filters, or generate a conversational reply
- **`flight_search` / `hotel_search` / `car_search`** — Run **in parallel** via LangGraph fan-out. Each embeds the query, applies pre-filters, and runs `$vectorSearch`
- **`aggregate`** — Collects all results, generates an LLM-powered natural-language summary, saves to chat persistence, marks search-progress as done, and triggers long-term memory extraction

State is defined in `orchestrator/state.py` as `TripSearchState` (TypedDict).

### Reserve Pipeline

```
START → create_reservation → END
```

Single-node graph using `TripReserveState`. Accepts partial selections (any combination of flight, hotel, car). Generates a human-readable reservation ID (`TRIP-YYYYMMDD-XXXX`) and stores it in Atlas.

---

## Sub-Agents

Each sub-agent is a self-contained LangGraph with two nodes:

```
embed_query → search_{category} → END
```

| Agent | Directory | Atlas Collection | State |
|-------|-----------|-----------------|-------|
| Flight | `agent_flight/` | `trip_flights` | `FlightSearchState` |
| Hotel | `agent_hotel/` | `trip_hotels` | `HotelSearchState` |
| Car | `agent_car/` | `trip_cars` | `CarSearchState` |

### Node 1: `embed_query`
Calls the Voyage AI REST API (`voyage-3-lite` model, 512 dimensions) to convert the natural-language query into a dense vector embedding.

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
- **Purpose**: Personalizes recommendations without the user repeating themselves

**Learning (extraction)**: After every orchestrator interaction, the LLM analyzes the conversation and extracts new travel preferences — preferred airlines, star ratings, budget constraints, car brands, travel style, group size, dislikes, etc. New facts are deduplicated against existing ones before saving.

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

### Local MongoDB (Platform)

| Collection | Purpose |
|------------|---------|
| `trip_search_progress` | Ephemeral — tracks partial search results for progressive UI streaming |
| `trip_seed_status` | Tracks data seeding progress and status |

---

## LLM Integration

The system supports multiple LLM providers via `shared/llm.py`:

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
5. **Preference extraction** — Long-term memory learning
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
- **Anthropic / Google GenAI / OpenAI / Groq** — LLM providers
- **Certifi** — SSL certificate handling for Atlas connections

## File Structure

```
trip_agents/
├── orchestrator/
│   ├── main.py          # Entry point — mode dispatch
│   ├── graph.py          # LangGraph pipelines (search + reserve)
│   └── state.py          # TypedDict state definitions
├── agent_flight/
│   ├── agent.py          # Flight sub-agent graph
│   ├── state.py          # FlightSearchState
│   └── nodes/
│       ├── embed_query.py
│       └── search_flights.py
├── agent_hotel/          # (same structure as agent_flight)
├── agent_car/            # (same structure as agent_flight)
├── shared/
│   ├── atlas.py          # Atlas client, vector_search, collection accessors
│   ├── mongo.py          # Local MongoDB client, team_settings, LLM config
│   ├── llm.py            # Multi-provider LLM wrapper
│   ├── voyage.py         # Voyage AI embedding client
│   ├── query_parser.py   # LLM-based intent + filter extraction
│   ├── memory.py         # Long-term preference extraction and injection
│   ├── config.py         # Environment variables and constants
│   ├── logger.py         # Logging configuration
│   └── utils.py          # Argument loading utilities
├── ui/
│   ├── tabs.json         # Tab definitions
│   └── tabs/
│       ├── trip_planner.html       # Chat + search UI
│       └── trip_reservations.html  # Reservations UI
├── seed_data.py          # Atlas data seeding script
├── run_config.json       # Stateless run configuration
├── requirements.txt
└── README.md
```
