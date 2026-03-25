"""Per-team LLM settings API.

Each agent team gets its own settings document (keyed by agent_id) in the
``team_settings`` MongoDB collection.  The Settings tab on the agent detail
page reads/writes through these endpoints.
"""

import logging
from datetime import datetime, timezone
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


def _ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


def _err(msg: str) -> dict:
    return {"success": False, "data": None, "error": msg}


class TeamSettingsUpdate(BaseModel):
    llm_provider: str | None = None
    llm_model: str | None = None
    api_keys: dict | None = None


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
        update["updated_at"] = datetime.now(timezone.utc)
        await db["team_settings"].update_one(
            {"_id": agent_id},
            {"$set": update},
            upsert=True,
        )

    logger.info("Team settings saved for %s: %s", agent_id, list(update.keys()))
    return _ok({"updated": list(update.keys())})
