"""Context-aware query parser for the trip booking chatbot.

Uses the configured LLM with conversation history to:
  1. Determine if the message is a NEW trip search request.
  2. Extract hard constraints for search filtering.
  3. Generate natural, conversational replies for non-search messages.
"""

import json
import re

from shared.llm import get_llm
from shared.prompt_loader import load_prompt_raw
from shared.logger import get_logger

logger = get_logger("shared.query_parser")


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
        system = load_prompt_raw("query_parser_system")
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
