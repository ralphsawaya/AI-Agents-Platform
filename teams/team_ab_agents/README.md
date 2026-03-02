# Team AB — Summarise & Title Pipeline

A two-agent pipeline that takes a text paragraph, produces a concise summary, and generates a compelling title for it.

---

## Agents

### Agent A — Summariser
Receives the raw input text (up to 500 words), validates it, and uses an LLM to produce a concise summary. The result is stored in MongoDB for downstream use.

**Nodes:** `input_node` → `summarize_node` → `output_node`

### Agent B — Title Generator
Receives the summary produced by Agent A and uses an LLM to generate a short, engaging title. The final title is stored alongside the summary in MongoDB.

**Nodes:** `input_node` → `title_node` → `output_node`

---

## Pipeline Flow

```
Input Text
    │
    ▼
Agent A (Summariser)
    │  validates input
    │  calls LLM → summary
    │  stores in MongoDB
    ▼
Agent B (Title Generator)
    │  calls LLM → title
    │  stores in MongoDB
    ▼
Output: { summary, title, text_id }
```

---

## Input

| Field | Type | Required | Limit |
|-------|------|----------|-------|
| `text` | Textarea | Yes | 500 words |

---

## Output

The pipeline returns a JSON object with:
- **`title`** — a short, engaging title for the text
- **`summary`** — a concise summary of the input paragraph
- **`text_id`** — a unique ID referencing the stored record in MongoDB

---

## LLM

Uses **Groq** (`llama-3.3-70b-versatile`) for both summarisation and title generation. Requires `GROQ_API_KEY` to be set in the platform environment.
