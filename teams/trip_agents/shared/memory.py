"""Long-term memory for trip agents.

Extracts and persists user preferences/facts from conversations into
Atlas trip_data.trip_longMemory, keyed by agent_id. These preferences
are injected into every new conversation so the chatbot personalises
recommendations without the user repeating themselves.

Each document in trip_longMemory:
  {
    "_id": <agent_id>,
    "preferences": [
      {"fact": "Prefers 5-star hotels", "category": "hotel", "learned_at": ...},
      {"fact": "Allergic to diesel cars", "category": "car", "learned_at": ...},
      ...
    ],
    "updated_at": <datetime>
  }
"""

import json
import re
from datetime import datetime, timezone

from shared.atlas import get_long_memory
from shared.llm import get_llm
from shared.prompt_loader import load_prompt_raw
from shared.logger import get_logger

logger = get_logger("shared.memory")

MAX_PREFERENCES = 30


def extract_preferences(messages: list, existing_prefs: list | None = None) -> list[dict]:
    """Use the LLM to extract new user preferences from a conversation."""
    if not messages:
        return []

    try:
        llm = get_llm()

        convo = "\n".join(
            f"{m.get('role', 'user').upper()}: {m.get('content', '')}"
            for m in messages if m.get("content")
        )

        existing_text = ""
        if existing_prefs:
            existing_text = "\n\nAlready-known preferences (do NOT repeat these):\n" + \
                "\n".join(f"- {p.get('fact', '')}" for p in existing_prefs)

        prompt = f"Conversation:\n{convo}{existing_text}"
        raw = llm.invoke(prompt, system=load_prompt_raw("memory_extraction"))

        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return []
        parsed = json.loads(match.group())
        if not isinstance(parsed, list):
            return []

        now = datetime.now(timezone.utc)
        results = []
        for item in parsed:
            if isinstance(item, dict) and item.get("fact"):
                results.append({
                    "fact": str(item["fact"]).strip(),
                    "category": str(item.get("category", "general")).strip(),
                    "learned_at": now,
                })
        return results

    except Exception as exc:
        logger.warning("Preference extraction failed: %s", exc)
        return []


def save_preferences(agent_id: str, new_prefs: list[dict]):
    """Merge new preferences into trip_longMemory (upsert, capped list)."""
    if not new_prefs or not agent_id:
        return
    try:
        col = get_long_memory()
        now = datetime.now(timezone.utc)

        doc = col.find_one({"_id": agent_id})
        existing = doc.get("preferences", []) if doc else []

        existing_facts = {p.get("fact", "").lower() for p in existing}
        unique_new = [p for p in new_prefs if p["fact"].lower() not in existing_facts]

        if not unique_new:
            logger.info("No new preferences to save for agent %s", agent_id)
            return

        combined = existing + unique_new
        if len(combined) > MAX_PREFERENCES:
            combined = combined[-MAX_PREFERENCES:]

        col.update_one(
            {"_id": agent_id},
            {"$set": {"preferences": combined, "updated_at": now}},
            upsert=True,
        )
        logger.info("Saved %d new preferences for agent %s (total: %d)",
                     len(unique_new), agent_id, len(combined))
    except Exception as exc:
        logger.error("Failed to save preferences: %s", exc)


def load_preferences(agent_id: str) -> list[dict]:
    """Load all stored preferences for an agent."""
    if not agent_id:
        return []
    try:
        col = get_long_memory()
        doc = col.find_one({"_id": agent_id})
        if doc:
            return doc.get("preferences", [])
    except Exception as exc:
        logger.warning("Failed to load preferences: %s", exc)
    return []


def format_preferences_for_prompt(prefs: list[dict]) -> str:
    """Format preferences into a string suitable for LLM system prompts."""
    if not prefs:
        return ""
    lines = ["The user has these known travel preferences (from past conversations):"]
    for p in prefs:
        lines.append(f"  - [{p.get('category', 'general')}] {p.get('fact', '')}")
    lines.append(
        "Use these to personalise recommendations. "
        "If a preference conflicts with the current request, follow the current request."
    )
    return "\n".join(lines)


def learn_from_thread(agent_id: str, messages: list):
    """End-of-conversation hook: extract and persist new preferences."""
    existing = load_preferences(agent_id)
    new_prefs = extract_preferences(messages, existing_prefs=existing)
    if new_prefs:
        save_preferences(agent_id, new_prefs)
        logger.info("Learned %d new preference(s) from thread", len(new_prefs))
    else:
        logger.info("No new preferences detected in thread")
