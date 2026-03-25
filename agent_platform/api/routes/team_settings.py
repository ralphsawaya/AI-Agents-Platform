"""Per-team LLM / Voice / integration settings API.

Each agent team gets its own settings document (keyed by agent_id) in the
``team_settings`` MongoDB collection.  The Settings tab on the agent detail
page reads/writes through these endpoints.

All runtime configuration — LLM provider, Voice provider, API keys,
integration keys — is stored exclusively in MongoDB and injected into the
agent subprocess environment by the executor.  No values are read from
.env files at runtime.
"""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from agent_platform.db.client import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["team-settings"])

# ---------------------------------------------------------------------------
# LLM providers
# ---------------------------------------------------------------------------

PROVIDER_MODELS = {
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    "claude": ["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
    "openai": ["gpt-4o", "gpt-4o-mini", "o3-mini"],
}

DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = "gemini-2.5-flash"

LLM_PROVIDER_TO_ENV_KEY: dict[str, str] = {
    "claude": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}

# ---------------------------------------------------------------------------
# Voice AI providers (shown only for teams that use voice)
# ---------------------------------------------------------------------------

VOICE_PROVIDERS: dict[str, list[str]] = {
    "bland": ["maya", "josh", "default"],
}

DEFAULT_VOICE_PROVIDER = "bland"
DEFAULT_VOICE_VOICE = "maya"

# ---------------------------------------------------------------------------
# Integration registry — known API keys with human-readable metadata.
# Teams declare which keys they need via os.getenv() in shared/config.py.
# The Settings UI reads the registry to render labelled input fields.
# ---------------------------------------------------------------------------
INTEGRATION_REGISTRY: dict[str, dict[str, str]] = {
    "VOICE_API_KEY": {
        "label": "Voice API Key",
        "description": "API key for the voice call provider",
        "category": "Voice & Telephony",
    },
    "TWILIO_ACCOUNT_SID": {
        "label": "Twilio Account SID",
        "description": "Twilio account identifier",
        "category": "Voice & Telephony",
    },
    "TWILIO_AUTH_TOKEN": {
        "label": "Twilio Auth Token",
        "description": "Twilio authentication token",
        "category": "Voice & Telephony",
    },
    "VAPI_API_KEY": {
        "label": "Vapi API Key",
        "description": "API key for Vapi voice platform",
        "category": "Voice & Telephony",
    },
    "GOOGLE_MAPS_API_KEY": {
        "label": "Google Maps API Key",
        "description": "API key for Google Maps / Places API",
        "category": "Maps & Location",
    },
    "BINANCE_API_KEY": {
        "label": "Binance API Key",
        "description": "Binance exchange API key",
        "category": "Trading",
    },
    "BINANCE_API_SECRET": {
        "label": "Binance API Secret",
        "description": "Binance exchange API secret",
        "category": "Trading",
    },
    "TRADINGVIEW_WEBHOOK_SECRET": {
        "label": "TradingView Webhook Secret",
        "description": "Secret for TradingView webhook authentication",
        "category": "Trading",
    },
}

_SKIP_KEYS = {
    "LLM_PROVIDER", "LLM_MODEL", "LLM_TEMPERATURE", "MAX_TOKENS",
    "VOICE_API_PROVIDER", "VOICE_API_KEY",
    "AGENT_ID", "AGENT_RUN_ID", "AGENT_ARGS",
    "GROQ_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY", "DEEPSEEK_API_KEY",
    "MONGODB_URI", "MONGODB_DB", "MONGODB_COLLECTION",
}


def _ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


def _err(msg: str) -> dict:
    return {"success": False, "data": None, "error": msg}


def _mask_key(value: str) -> str:
    """Return a masked version of a secret for display (e.g. 'sk-abc…xyz')."""
    if not value:
        return ""
    if len(value) <= 8:
        return "••••••••"
    return value[:4] + "••••" + value[-4:]


_GETENV_RE = re.compile(r"""os\.getenv\(\s*['"]([A-Z][A-Z0-9_]+)['"]""")


def _scan_required_keys(agent: dict) -> list[str]:
    """Scan the team's Python source for os.getenv() calls and return env var
    names that are integration keys (present in INTEGRATION_REGISTRY and not
    in _SKIP_KEYS).  This replaces .env parsing — the source code itself
    declares what keys the team needs.
    """
    upload_path = agent.get("upload_path", "")
    root_folder = agent.get("root_folder", "")
    if not upload_path:
        return []

    root = Path(upload_path) / root_folder
    if not root.is_dir():
        return []

    found: set[str] = set()
    for py_file in root.rglob("*.py"):
        try:
            text = py_file.read_text(errors="ignore")
        except OSError:
            continue
        for match in _GETENV_RE.finditer(text):
            key = match.group(1)
            if key not in _SKIP_KEYS and key in INTEGRATION_REGISTRY:
                found.add(key)

    return sorted(found)


def _team_has_voice(agent: dict) -> bool:
    """Return True if the team's source code references VOICE_API_KEY or
    VOICE_API_PROVIDER, indicating it uses voice capabilities.
    """
    upload_path = agent.get("upload_path", "")
    root_folder = agent.get("root_folder", "")
    if not upload_path:
        return False
    root = Path(upload_path) / root_folder
    if not root.is_dir():
        return False
    for py_file in root.rglob("*.py"):
        try:
            text = py_file.read_text(errors="ignore")
        except OSError:
            continue
        if "VOICE_API_KEY" in text or "VOICE_API_PROVIDER" in text:
            return True
    return False


class TeamSettingsUpdate(BaseModel):
    llm_provider: str | None = None
    llm_model: str | None = None
    api_keys: dict | None = None
    voice_provider: str | None = None
    voice_voice: str | None = None
    voice_api_key: str | None = None


class IntegrationKeysUpdate(BaseModel):
    keys: dict[str, str]


@router.get("/{agent_id}/settings")
async def get_team_settings(agent_id: str):
    """Return persisted LLM + Voice settings for an agent team."""
    db = get_database()
    doc = await db["team_settings"].find_one({"_id": agent_id})

    agent = await db["agents"].find_one({"_id": agent_id})
    has_voice = _team_has_voice(agent) if agent else False

    if not doc:
        doc = {}

    doc.pop("_id", None)
    doc.pop("updated_at", None)
    doc.pop("agent_name", None)

    raw_integ_keys = doc.pop("integration_keys", {}) or {}

    doc.setdefault("api_keys", {})
    doc["providers"] = PROVIDER_MODELS
    doc.setdefault("llm_provider", DEFAULT_PROVIDER)
    doc.setdefault("llm_model", DEFAULT_MODEL)

    doc["has_voice"] = has_voice
    if has_voice:
        doc["voice_providers"] = VOICE_PROVIDERS
        doc.setdefault("voice_provider", DEFAULT_VOICE_PROVIDER)
        doc.setdefault("voice_voice", DEFAULT_VOICE_VOICE)
        doc["voice_api_key_masked"] = _mask_key(raw_integ_keys.get("VOICE_API_KEY", ""))

    return _ok(doc)


@router.put("/{agent_id}/settings")
async def update_team_settings(agent_id: str, body: TeamSettingsUpdate):
    """Save LLM + Voice settings for an agent team."""
    db = get_database()

    update: dict[str, Any] = {}
    if body.llm_provider is not None:
        update["llm_provider"] = body.llm_provider
    if body.llm_model is not None:
        update["llm_model"] = body.llm_model
    if body.voice_provider is not None:
        update["voice_provider"] = body.voice_provider
    if body.voice_voice is not None:
        update["voice_voice"] = body.voice_voice

    existing = None
    if body.api_keys or body.voice_api_key:
        existing = await db["team_settings"].find_one({"_id": agent_id})

    if body.api_keys:
        merged_keys = (existing or {}).get("api_keys", {})
        merged_keys.update(body.api_keys)
        update["api_keys"] = merged_keys

    if body.voice_api_key:
        integ_keys = (existing or {}).get("integration_keys", {})
        integ_keys["VOICE_API_KEY"] = body.voice_api_key
        update["integration_keys"] = integ_keys

    if update:
        agent = await db["agents"].find_one({"_id": agent_id}, {"name": 1})
        if agent:
            update["agent_name"] = agent.get("name", "")
        update["updated_at"] = datetime.now(timezone.utc)
        await db["team_settings"].update_one(
            {"_id": agent_id},
            {"$set": update},
            upsert=True,
        )

    logger.info("Team settings saved for %s: %s", agent_id, list(update.keys()))
    return _ok({"updated": list(update.keys())})


# -- Integration keys ---------------------------------------------------------

@router.get("/{agent_id}/integrations")
async def get_integrations(agent_id: str):
    """Return integration keys required by this team, with saved values masked."""
    db = get_database()

    agent = await db["agents"].find_one({"_id": agent_id})
    if not agent:
        return _err("Agent not found")

    env_keys = _scan_required_keys(agent)

    doc = await db["team_settings"].find_one({"_id": agent_id})
    saved_keys: dict[str, str] = (doc or {}).get("integration_keys", {})

    categories: dict[str, list[dict]] = {}
    for key in env_keys:
        reg = INTEGRATION_REGISTRY.get(key)
        entry = {
            "key": key,
            "label": reg["label"] if reg else key.replace("_", " ").title(),
            "description": reg["description"] if reg else "",
            "category": reg["category"] if reg else "Other",
            "has_value": bool(saved_keys.get(key)),
            "masked_value": _mask_key(saved_keys.get(key, "")),
        }
        cat = entry["category"]
        categories.setdefault(cat, [])
        categories[cat].append(entry)

    return _ok({
        "categories": categories,
        "total_keys": len(env_keys),
        "configured_keys": sum(1 for k in env_keys if saved_keys.get(k)),
    })


@router.put("/{agent_id}/integrations")
async def update_integrations(agent_id: str, body: IntegrationKeysUpdate):
    """Save integration key values for a team. Empty strings clear the key."""
    db = get_database()

    existing = await db["team_settings"].find_one({"_id": agent_id})
    merged: dict[str, str] = (existing or {}).get("integration_keys", {})

    changed = []
    for key, value in body.keys.items():
        value = value.strip()
        if value:
            merged[key] = value
            changed.append(key)
        else:
            merged.pop(key, None)
            changed.append(key)

    update_fields: dict[str, Any] = {
        "integration_keys": merged,
        "updated_at": datetime.now(timezone.utc),
    }
    agent = await db["agents"].find_one({"_id": agent_id}, {"name": 1})
    if agent:
        update_fields["agent_name"] = agent.get("name", "")

    await db["team_settings"].update_one(
        {"_id": agent_id},
        {"$set": update_fields},
        upsert=True,
    )

    logger.info("Integration keys updated for %s: %s", agent_id, changed)
    return _ok({"updated": changed})
