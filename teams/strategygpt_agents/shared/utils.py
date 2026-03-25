"""Shared utility functions."""

import json
import os
import re


def load_args() -> dict:
    """Load runtime arguments from the AGENT_ARGS environment variable."""
    raw = os.getenv("AGENT_ARGS", "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def parse_categories(raw: str) -> list[str]:
    """Split a comma-separated category string into a cleaned list."""
    if not raw:
        return []
    return [c.strip().lower() for c in raw.split(",") if c.strip()]


def format_phone_us(phone: str) -> str:
    """Normalise a US phone number to E.164 (+1XXXXXXXXXX). Returns '' on failure."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return ""
