"""Per-team LLM settings and integration keys API.

Each agent team gets its own settings document (keyed by agent_id) in the
``team_settings`` MongoDB collection.  The Settings tab on the agent detail
page reads/writes through these endpoints.

Integration keys (API keys for third-party services) are stored in
``integration_keys`` within the same document and injected into the agent's
environment at runtime by the executor.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from agent_platform.db.client import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["team-settings"])

PROVIDER_MODELS = {
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    "claude": ["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
    "openai": ["gpt-4o", "gpt-4o-mini", "o3-mini"],
}

DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = "gemini-2.5-flash"

# ---------------------------------------------------------------------------
# Integration registry — known API keys with human-readable metadata.
# Teams declare which keys they need by including them in their .env file.
# The Settings UI reads the registry to render labelled input fields.
# ---------------------------------------------------------------------------
INTEGRATION_REGISTRY: dict[str, dict[str, str]] = {
    # Voice / telephony
    "VOICE_API_KEY": {
        "label": "Voice API Key",
        "description": "API key for the voice call provider (Bland.ai, Vapi, Twilio, etc.)",
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
    # Maps & location
    "GOOGLE_MAPS_API_KEY": {
        "label": "Google Maps API Key",
        "description": "API key for Google Maps / Places API",
        "category": "Maps & Location",
    },
    # LLM keys (also in LLM section, but exposed here for completeness)
    "GROQ_API_KEY": {
        "label": "Groq API Key",
        "description": "API key for Groq inference",
        "category": "LLM Providers",
    },
    "GEMINI_API_KEY": {
        "label": "Google Gemini API Key",
        "description": "API key for Google Gemini models",
        "category": "LLM Providers",
    },
    "ANTHROPIC_API_KEY": {
        "label": "Anthropic API Key",
        "description": "API key for Claude models",
        "category": "LLM Providers",
    },
    "OPENAI_API_KEY": {
        "label": "OpenAI API Key",
        "description": "API key for OpenAI / GPT models",
        "category": "LLM Providers",
    },
    "DEEPSEEK_API_KEY": {
        "label": "DeepSeek API Key",
        "description": "API key for DeepSeek models",
        "category": "LLM Providers",
    },
    # Trading
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
    # Database
    "MONGODB_URI": {
        "label": "MongoDB URI",
        "description": "MongoDB connection string",
        "category": "Database",
    },
}

# Keys that should NOT be shown in the Integrations UI.
# LLM keys are excluded because they are managed via the LLM Configuration
# dropdown section (which already saves them to api_keys in team_settings).
_SKIP_KEYS = {
    "LLM_PROVIDER", "LLM_MODEL", "VOICE_API_PROVIDER",
    "AGENT_ID", "AGENT_RUN_ID", "AGENT_ARGS",
    "GROQ_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY", "DEEPSEEK_API_KEY",
}


def _ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


def _err(msg: str) -> dict:
    return {"success": False, "data": None, "error": msg}


def _mask_key(value: str) -> str:
    """Return a masked version of a secret for display (e.g. 'sk-abc…xyz')."""
    if not value or value == "PLATFORM_MANAGED":
        return ""
    if len(value) <= 8:
        return "••••••••"
    return value[:4] + "••••" + value[-4:]


def _scan_env_keys(agent: dict) -> list[str]:
    """Parse the team's .env file and return env var names that look like
    integration keys (present in INTEGRATION_REGISTRY or unknown but non-skip).
    """
    upload_path = agent.get("upload_path", "")
    root_folder = agent.get("root_folder", "")
    if not upload_path:
        return []

    env_path = Path(upload_path) / root_folder / ".env"
    if not env_path.is_file():
        return []

    keys: list[str] = []
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.partition("=")[0].strip()
        if key and key not in _SKIP_KEYS:
            keys.append(key)
    return keys


class TeamSettingsUpdate(BaseModel):
    llm_provider: str | None = None
    llm_model: str | None = None
    api_keys: dict | None = None


class IntegrationKeysUpdate(BaseModel):
    keys: dict[str, str]


@router.get("/{agent_id}/settings")
async def get_team_settings(agent_id: str):
    """Return persisted LLM settings for an agent team."""
    db = get_database()
    doc = await db["team_settings"].find_one({"_id": agent_id})
    if not doc:
        return _ok({
            "llm_provider": DEFAULT_PROVIDER,
            "llm_model": DEFAULT_MODEL,
            "api_keys": {},
            "providers": PROVIDER_MODELS,
        })

    doc.pop("_id", None)
    doc.pop("updated_at", None)

    doc.setdefault("api_keys", {})
    doc["providers"] = PROVIDER_MODELS
    doc.setdefault("llm_provider", DEFAULT_PROVIDER)
    doc.setdefault("llm_model", DEFAULT_MODEL)
    return _ok(doc)


@router.put("/{agent_id}/settings")
async def update_team_settings(agent_id: str, body: TeamSettingsUpdate):
    """Save LLM settings for an agent team."""
    db = get_database()

    update: dict[str, Any] = {}
    if body.llm_provider is not None:
        update["llm_provider"] = body.llm_provider
    if body.llm_model is not None:
        update["llm_model"] = body.llm_model

    if body.api_keys:
        existing = await db["team_settings"].find_one({"_id": agent_id})
        merged_keys = (existing or {}).get("api_keys", {})
        merged_keys.update(body.api_keys)
        update["api_keys"] = merged_keys

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

    env_keys = _scan_env_keys(agent)

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
