"""Voice API adapter — pluggable interface supporting Bland.ai, Vapi, and Twilio.

The active provider is selected by VOICE_API_PROVIDER in shared/config.py.
Each provider implements place_call() and get_call_status().
"""

import requests

from shared.config import VOICE_API_KEY, VOICE_API_PROVIDER
from shared.logger import get_logger

logger = get_logger("voice_caller.voice_tools")

# ---------------------------------------------------------------------------
# Bland.ai adapter
# ---------------------------------------------------------------------------

BLAND_BASE_URL = "https://api.bland.ai/v1"


def _bland_place_call(phone: str, script: str) -> dict:
    """Place a call via Bland.ai Send Call API."""
    headers = {
        "Authorization": VOICE_API_KEY,
        "Content-Type": "application/json",
    }
    body = {
        "phone_number": phone,
        "task": script,
        "voice": "maya",
        "wait_for_greeting": True,
        "record": True,
        "max_duration": 120,
    }
    resp = requests.post(f"{BLAND_BASE_URL}/calls", json=body, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return {"call_id": data.get("call_id", ""), "status": "initiated"}


def _bland_get_status(call_id: str) -> dict:
    """Get call status from Bland.ai."""
    headers = {"Authorization": VOICE_API_KEY}
    resp = requests.get(f"{BLAND_BASE_URL}/calls/{call_id}", headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    completed = data.get("completed", False)
    answered = data.get("answered_by") is not None

    disposition = "no_answer"
    if completed and answered:
        analysis = data.get("analysis", {})
        disposition = analysis.get("disposition", "no_answer")

    return {
        "completed": completed,
        "disposition": disposition,
        "duration": data.get("call_length", 0),
        "transcript": data.get("concatenated_transcript", ""),
    }


# ---------------------------------------------------------------------------
# Vapi adapter (stub)
# ---------------------------------------------------------------------------

def _vapi_place_call(phone: str, script: str) -> dict:
    """Place a call via Vapi — stub implementation."""
    logger.warning("Vapi adapter is a stub; implement with your Vapi API key")
    return {"call_id": "vapi_stub", "status": "stub"}


def _vapi_get_status(call_id: str) -> dict:
    """Get call status from Vapi — stub."""
    return {"completed": True, "disposition": "no_answer", "duration": 0, "transcript": ""}


# ---------------------------------------------------------------------------
# Twilio adapter (stub)
# ---------------------------------------------------------------------------

def _twilio_place_call(phone: str, script: str) -> dict:
    """Place a call via Twilio — stub implementation."""
    logger.warning("Twilio adapter is a stub; implement with your Twilio credentials")
    return {"call_id": "twilio_stub", "status": "stub"}


def _twilio_get_status(call_id: str) -> dict:
    """Get call status from Twilio — stub."""
    return {"completed": True, "disposition": "no_answer", "duration": 0, "transcript": ""}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_PROVIDERS = {
    "bland": (_bland_place_call, _bland_get_status),
    "vapi": (_vapi_place_call, _vapi_get_status),
    "twilio": (_twilio_place_call, _twilio_get_status),
}


def place_call(phone: str, script: str, provider: str | None = None) -> dict:
    """Place a call using the configured or specified voice provider."""
    provider = provider or VOICE_API_PROVIDER
    funcs = _PROVIDERS.get(provider)
    if not funcs:
        raise ValueError(f"Unknown voice provider: {provider}")
    return funcs[0](phone, script)


def get_call_status(call_id: str, provider: str | None = None) -> dict:
    """Get the status of a call from the configured or specified voice provider."""
    provider = provider or VOICE_API_PROVIDER
    funcs = _PROVIDERS.get(provider)
    if not funcs:
        raise ValueError(f"Unknown voice provider: {provider}")
    return funcs[1](call_id)
