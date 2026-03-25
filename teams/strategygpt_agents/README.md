# StrategyGPT — SMB Website Outreach Pipeline

A three-agent pipeline that scans Google Maps for small and medium businesses without websites, qualifies them, and places AI voice calls to pitch a free website creation offer. Records each lead's response (interested / not interested).

---

## Agents

### Agent Lead Sourcer
Queries the Google Maps Places API for businesses in a target city and category. Filters by: minimum 10 reviews, minimum 3.5 rating, no existing website, and a valid phone number. Stores matching leads in MongoDB.

**Nodes:** `search_places` → `filter_leads` → `store_leads`

### Agent Lead Qualifier
Fetches new leads from MongoDB, validates phone numbers (US format), checks against an internal Do Not Call list, and uses an LLM to generate a personalised call script for each business.

**Nodes:** `fetch_new_leads` → `enrich_leads` → `generate_scripts`

### Agent Voice Caller
Places AI voice calls to qualified leads using a pluggable voice API (Bland.ai by default, with stubs for Vapi and Twilio). Delivers the personalised pitch and records the outcome: interested, not interested, voicemail, callback requested, or no answer.

**Nodes:** `fetch_qualified_leads` → `initiate_calls` → `record_outcomes`

---

## Pipeline Flow

```
Target City + Categories
    │
    ▼
Agent Lead Sourcer
    │  queries Google Maps Places API
    │  filters: reviews ≥ 10, rating ≥ 3.5, no website
    │  stores leads in MongoDB (status: "new")
    ▼
Agent Lead Qualifier
    │  validates phone numbers
    │  checks DNC list
    │  generates personalised call scripts via LLM
    │  updates leads in MongoDB (status: "qualified")
    ▼
Agent Voice Caller
    │  places AI voice calls via Bland.ai / Vapi / Twilio
    │  records outcome in MongoDB
    ▼
Output: leads marked as interested / not_interested / voicemail / callback / no_answer
```

---

## Pipeline Modes

| Mode | What it runs | Use when |
|------|-------------|----------|
| `sourcing` | Lead Sourcer → Lead Qualifier | You want to build up a lead list without calling yet |
| `outreach` | Voice Caller only | You already have qualified leads and want to start calling |
| `full` | Lead Sourcer → Lead Qualifier → Voice Caller | End-to-end: scan, qualify, and call in one run |

---

## Input

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `mode` | Select | Yes | `full` |
| `city` | Text | No | `Austin, TX` |
| `categories` | Text (comma-separated) | No | `restaurant, plumber` |
| `max_leads` | Number | No | `50` |

---

## Lead Status Lifecycle

```
new → qualified → interested
                → not_interested
                → voicemail
                → callback_requested
                → no_answer
new → invalid (bad phone / DNC)
```

Leads marked **interested** are your handoff point — build the website using your own tool, outside this pipeline.

---

## Required API Keys

| Key | Service | Purpose |
|-----|---------|---------|
| `GOOGLE_MAPS_API_KEY` | Google Cloud | Places API (Text Search) for lead sourcing |
| `VOICE_API_KEY` | Bland.ai / Vapi / Twilio | AI voice calling |
| `GEMINI_API_KEY` | Google Cloud | LLM for call script generation (default provider) |

Set these in the `.env` file, in the platform environment, or via the **Settings** tab on the agent detail page.

---

## LLM

Uses **Google Gemini** (`gemini-2.5-flash`) by default for call script generation. Also supports Anthropic Claude, DeepSeek, Groq, and OpenAI. The LLM provider and model can be configured from the **Settings** tab on the agent detail page (persisted to MongoDB), or via the `LLM_PROVIDER` / `LLM_MODEL` environment variables as fallback.

---

## Legal Notes

- B2B cold calling in the USA is generally permitted under TCPA
- The pipeline respects business hours (8am–9pm local time)
- An internal DNC (Do Not Call) list is maintained in MongoDB
- All call outcomes and transcripts are logged for compliance
