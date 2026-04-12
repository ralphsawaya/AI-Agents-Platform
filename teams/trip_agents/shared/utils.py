"""Shared utility functions."""

import json
import os


def load_args() -> dict:
    """Load runtime arguments from the AGENT_ARGS environment variable."""
    raw = os.getenv("AGENT_ARGS", "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
