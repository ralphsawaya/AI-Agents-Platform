"""Classify user chat messages into intents: search, cancel, or unknown.

Uses the configured LLM for reliable intent detection and entity extraction.
"""

import json
import re

from shared.llm import get_llm
from shared.logger import get_logger

logger = get_logger("shared.intent")

_SYSTEM = """You are an intent classifier for a trip booking chatbot.
Given a user message, determine the intent and extract relevant entities.

Possible intents:
- "search": The user wants to search for flights, hotels, cars, or plan a trip.
- "cancel": The user wants to cancel or delete an existing reservation.

Return ONLY a JSON object with these fields:
- "intent": one of "search" or "cancel"
- "reservation_id": (only for cancel) the reservation ID mentioned, e.g. "TRIP-20260412-K7X3"

Rules:
- If the user mentions cancelling, deleting, or removing a reservation, the intent is "cancel".
- Look for reservation IDs matching the pattern TRIP-XXXXXXXX-XXXX.
- If unsure, default to "search".
- Return ONLY valid JSON, no explanation."""


def classify_intent(message: str) -> dict:
    """Return {"intent": "search"|"cancel", "reservation_id": "..." or None}."""
    quick = _quick_check(message)
    if quick:
        return quick

    try:
        llm = get_llm()
        raw = llm.invoke(
            f'Classify this message:\n"{message}"',
            system=_SYSTEM,
        )
        parsed = _extract_json(raw)
        if isinstance(parsed, dict) and parsed.get("intent") in ("search", "cancel"):
            result = {"intent": parsed["intent"], "reservation_id": parsed.get("reservation_id")}
            logger.info("LLM classified intent: %s", result)
            return result
    except Exception as exc:
        logger.warning("Intent classification failed, defaulting to search: %s", exc)

    return {"intent": "search", "reservation_id": None}


_CANCEL_PATTERNS = re.compile(
    r'\b(cancel|delete|remove|revoke|annul)\b.*\breservation\b'
    r'|\breservation\b.*\b(cancel|delete|remove|revoke|annul)\b',
    re.IGNORECASE,
)
_RESERVATION_ID_PATTERN = re.compile(r'TRIP-\d{8}-[A-Z0-9]{4}')


def _quick_check(message: str) -> dict | None:
    """Fast regex-based check before calling the LLM."""
    res_id_match = _RESERVATION_ID_PATTERN.search(message)
    if res_id_match and _CANCEL_PATTERNS.search(message):
        return {"intent": "cancel", "reservation_id": res_id_match.group()}
    return None


def _extract_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return {}
