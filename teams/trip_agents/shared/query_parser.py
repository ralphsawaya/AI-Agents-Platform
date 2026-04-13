"""Context-aware query parser for the trip booking chatbot.

Uses the configured LLM with conversation history to:
  1. Detect whether the message is trip-related or conversational.
  2. For conversational messages: route directly to the LLM for a natural reply.
  3. For trip searches: extract hard constraints for search filtering.
"""

import json
import re

from shared.llm import get_llm
from shared.prompt_loader import load_prompt_raw
from shared.logger import get_logger

logger = get_logger("shared.query_parser")

_CONVERSATIONAL_PATTERNS = re.compile(
    r"^\s*("
    r"h(i|ello|ey|owdy|ola)|"
    r"good\s*(morning|afternoon|evening|night|day)|"
    r"how\s+(are|r)\s+(you|u)|"
    r"what('s|\s+is)\s+up|"
    r"sup|yo|"
    r"thanks?(\s+you)?|thank\s+you|"
    r"great|awesome|cool|nice|ok(ay)?|"
    r"bye|goodbye|see\s+you|later|"
    r"who\s+are\s+you|what\s+(can|do)\s+you\s+do|"
    r"how\s+does\s+this\s+work|help\s*$|"
    r"what\s+is\s+this|tell\s+me\s+about\s+(yourself|you)"
    r")\s*[?!.]*\s*$",
    re.IGNORECASE,
)

_TRIP_KEYWORDS = re.compile(
    r"\b("
    r"flight|fly|airport|airline|boarding|departure|arrival|layover|stopover|"
    r"hotel|hostel|accommodation|stay|room|book(ing)?|"
    r"car\s+rental|rent\s+a\s+car|rental|drive|"
    r"travel|trip|vacation|holiday|getaway|"
    r"destination|city|country|"
    r"economy|business\s+class|first\s+class|premium|"
    r"from\s+\w+\s+to\s+\w+"
    r")\b",
    re.IGNORECASE,
)

_CHAT_SYSTEM = (
    "You are a friendly, knowledgeable trip booking assistant. "
    "You help users find flights, hotels, and rental cars. "
    "You have a warm, conversational tone — never robotic.\n\n"
    "The user sent a message that is NOT a trip search request. "
    "Respond naturally and conversationally. If appropriate, gently remind them "
    "you can help with flights, hotels, and car rentals."
)


def _is_trip_related(query: str, chat_history: list | None = None) -> bool:
    """Fast two-tier check: regex first, then LLM fallback for ambiguous cases."""
    text = query.strip()

    if _CONVERSATIONAL_PATTERNS.match(text):
        logger.info("Quick-match: conversational pattern detected")
        return False

    if _TRIP_KEYWORDS.search(text):
        logger.info("Quick-match: trip keyword detected")
        return True

    if len(text.split()) <= 5 and not _TRIP_KEYWORDS.search(text):
        logger.info("Short non-trip message, treating as conversational")
        return False

    try:
        llm = get_llm()
        prompt = (
            f'Is the following message a request to search for flights, hotels, '
            f'or car rentals for a trip? Answer ONLY "yes" or "no".\n\n'
            f'Message: "{text}"'
        )
        raw = llm.invoke(prompt).strip().lower()
        is_trip = raw.startswith("yes")
        logger.info("LLM trip-relevance check: %r → %s", raw[:30], is_trip)
        return is_trip
    except Exception as exc:
        logger.warning("Trip-relevance LLM check failed: %s", exc)
        return False


def _get_conversational_reply(query: str, chat_history: list | None = None) -> str:
    """Send a non-trip message directly to the LLM for a natural response."""
    try:
        llm = get_llm()
        parts = []
        if chat_history:
            parts.append("Conversation so far:")
            for msg in (chat_history or [])[-6:]:
                role = msg.get("role", "user").upper()
                content = msg.get("content", "")
                if len(content) > 300:
                    content = content[:300] + "..."
                parts.append(f"  {role}: {content}")
            parts.append("")
        parts.append(f"User: {query}")
        prompt = "\n".join(parts)
        reply = llm.invoke(prompt, system=_CHAT_SYSTEM).strip().strip('"')
        logger.info("Conversational LLM reply: %s", reply[:120])
        return reply
    except Exception as exc:
        logger.warning("Conversational LLM call failed: %s", exc)
        return (
            "I'm your trip booking assistant! Tell me where you'd like to travel "
            "and I'll find the best flights, hotels, and car rentals for you."
        )


def parse_query_filters(query: str, chat_history: list | None = None,
                        user_prefs: str = "") -> dict:
    """Analyze a message with conversation context and long-term memory.

    First checks if the message is trip-related. If not, routes directly to
    the LLM for a conversational reply (no JSON parsing needed).

    Args:
        query: The user's latest message.
        chat_history: List of {"role": "user"|"assistant", "content": "..."} dicts.
        user_prefs: Formatted long-term preferences string (from memory.py).

    Returns:
        {"is_search": bool, "reply": str|None, "flight": {...}, "hotel": {...}, "car": {...}}
    """
    if not _is_trip_related(query, chat_history):
        reply = _get_conversational_reply(query, chat_history)
        return {"is_search": False, "reply": reply, "flight": {}, "hotel": {}, "car": {}}

    try:
        llm = get_llm()
        system = load_prompt_raw("query_parser_system")
        if user_prefs:
            system = system + "\n\n" + user_prefs
        prompt = _build_search_prompt(query, chat_history)
        raw = llm.invoke(prompt, system=system)
        parsed = _extract_json(raw)
        if not isinstance(parsed, dict) or not parsed:
            logger.warning("JSON extraction returned empty/invalid result, falling back to reply")
            reply = _get_conversational_reply(query, chat_history)
            return {"is_search": False, "reply": reply, "flight": {}, "hotel": {}, "car": {}}

        is_search = parsed.get("is_search", True)

        if not is_search:
            reply = parsed.get("reply") or _get_conversational_reply(query, chat_history)
            logger.info("Parser returned non-search — reply: %s", reply[:120])
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
        logger.warning("Query parsing failed, falling back to conversational reply: %s", exc)
        reply = _get_conversational_reply(query, chat_history)
        return {"is_search": False, "reply": reply, "flight": {}, "hotel": {}, "car": {}}


def _build_search_prompt(query: str, chat_history: list | None) -> str:
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


def _extract_json(text: str) -> dict:
    text = text.strip()
    # Find the first '{' and match braces to find the complete JSON object,
    # rather than greedy-matching from first '{' to last '}'.
    start = text.find('{')
    if start == -1:
        return {}
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return {}
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
