"""Context-aware query parser for the trip booking chatbot.

Uses the configured LLM with conversation history to:
  1. Determine if the message is a NEW trip search request.
  2. Extract hard constraints for search filtering.
  3. Generate natural, conversational replies for non-search messages.
"""

import json
import re

from shared.llm import get_llm
from shared.logger import get_logger

logger = get_logger("shared.query_parser")

_SYSTEM = """You are a friendly, knowledgeable trip booking assistant. You help users find flights,
hotels, and rental cars. You have a warm, conversational tone — never robotic.

Given the conversation history and the user's latest message, you must decide what to do.

Return ONLY a JSON object with these fields:

- "is_search": boolean — true ONLY if this is a NEW trip search request.
- "reply": string — a natural, conversational response (REQUIRED when is_search is false).
- "flight": object of flight filters (only when is_search is true)
- "hotel": object of hotel filters (only when is_search is true)
- "car": object of car filters (only when is_search is true)

## When is_search should be FALSE:

- Greetings, small talk, thanks, questions about the system
- Follow-up questions or comments about PREVIOUS search results
  (e.g. "why didn't you find X?", "can you explain this result?", "the hotel isn't what I wanted")
- User asking about results already shown — you should reference what was found/not found
- Any message that does NOT request a brand new trip search

When is_search is false, write a helpful, human reply in "reply". Be specific:
- If the user asks about missing results, explain that the search found the closest matches
  available and suggest they try different criteria.
- If the user comments on results, acknowledge and offer to search again with adjusted criteria.
- Reference the conversation context — don't give generic responses.

## When is_search should be TRUE:

- User explicitly requests a NEW search for flights, hotels, or cars
- User provides new travel details (different destination, dates, preferences)
- User says "search again", "find me something else", "try with different criteria"

## Filter fields (only include if EXPLICITLY mentioned):

flight: origin_city, destination_city, travel_class (economy/premium economy/business/first)
hotel: city, stars (integer 2-5)
car: color (lowercase), make, category (economy/compact/mid-size/full-size/SUV/luxury/convertible),
     transmission (automatic/manual), fuel_type (gasoline/diesel/hybrid/electric), pickup_city

## Filter rules:
- Only include a field if the user EXPLICITLY mentioned it.
- For hotel city: if user mentions a destination city, use that as hotel city.
- For car pickup_city: if user mentions a destination city, use that as pickup_city.
- Return empty {} for a filter category if no filters apply.

Return ONLY valid JSON, no markdown, no explanation."""


def parse_query_filters(query: str, chat_history: list | None = None,
                        user_prefs: str = "") -> dict:
    """Analyze a message with conversation context and long-term memory.

    Args:
        query: The user's latest message.
        chat_history: List of {"role": "user"|"assistant", "content": "..."} dicts.
        user_prefs: Formatted long-term preferences string (from memory.py).

    Returns:
        {"is_search": bool, "reply": str|None, "flight": {...}, "hotel": {...}, "car": {...}}
    """
    try:
        llm = get_llm()
        system = _SYSTEM
        if user_prefs:
            system = system + "\n\n" + user_prefs
        prompt = _build_prompt(query, chat_history)
        raw = llm.invoke(prompt, system=system)
        parsed = _extract_json(raw)
        if not isinstance(parsed, dict):
            return _empty_search()

        is_search = parsed.get("is_search", True)

        if not is_search:
            reply = parsed.get("reply", "I'm here to help you find the perfect trip! What destination are you thinking about?")
            logger.info("Non-search — reply: %s", reply[:120])
            return {"is_search": False, "reply": reply, "flight": {}, "hotel": {}, "car": {}}

        result = {
            "is_search": True,
            "reply": None,
            "flight": _clean_flight_filters(parsed.get("flight", {})),
            "hotel": _clean_hotel_filters(parsed.get("hotel", {})),
            "car": _clean_car_filters(parsed.get("car", {})),
        }
        logger.info("Search — filters: %s",
                     json.dumps({k: v for k, v in result.items() if k not in ("is_search", "reply")}))
        return result
    except Exception as exc:
        logger.warning("Query parsing failed, proceeding as search: %s", exc)
        return _empty_search()


def _build_prompt(query: str, chat_history: list | None) -> str:
    parts = []
    if chat_history:
        parts.append("Conversation so far:")
        for msg in chat_history[-6:]:
            role = msg.get("role", "user").upper()
            content = msg.get("content", "")
            if len(content) > 300:
                content = content[:300] + "..."
            parts.append(f"  {role}: {content}")
        parts.append("")

    parts.append(f'Latest user message: "{query}"')
    parts.append("")
    parts.append("Return JSON only:")
    return "\n".join(parts)


def _empty_search():
    return {"is_search": True, "reply": None, "flight": {}, "hotel": {}, "car": {}}


def _extract_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return {}


_VALID_CLASSES = {"economy", "premium economy", "business", "first"}
_VALID_CATEGORIES = {"economy", "compact", "mid-size", "full-size", "SUV", "luxury", "convertible"}
_VALID_TRANSMISSIONS = {"automatic", "manual"}
_VALID_FUELS = {"gasoline", "diesel", "hybrid", "electric"}


def _clean_flight_filters(f: dict) -> dict:
    if not isinstance(f, dict):
        return {}
    out = {}
    if f.get("origin_city"):
        out["origin_city"] = str(f["origin_city"])
    if f.get("destination_city"):
        out["destination_city"] = str(f["destination_city"])
    if f.get("travel_class") and str(f["travel_class"]).lower() in _VALID_CLASSES:
        out["travel_class"] = str(f["travel_class"]).lower()
    return out


def _clean_hotel_filters(h: dict) -> dict:
    if not isinstance(h, dict):
        return {}
    out = {}
    if h.get("city"):
        out["city"] = str(h["city"])
    if h.get("stars") and isinstance(h["stars"], (int, float)):
        out["stars"] = int(h["stars"])
    return out


def _clean_car_filters(c: dict) -> dict:
    if not isinstance(c, dict):
        return {}
    out = {}
    if c.get("color"):
        out["color"] = str(c["color"]).lower()
    if c.get("make"):
        out["make"] = str(c["make"])
    if c.get("category") and str(c["category"]).lower() in _VALID_CATEGORIES:
        out["category"] = str(c["category"]).lower()
    if c.get("transmission") and str(c["transmission"]).lower() in _VALID_TRANSMISSIONS:
        out["transmission"] = str(c["transmission"]).lower()
    if c.get("fuel_type") and str(c["fuel_type"]).lower() in _VALID_FUELS:
        out["fuel_type"] = str(c["fuel_type"]).lower()
    if c.get("pickup_city"):
        out["pickup_city"] = str(c["pickup_city"])
    return out
