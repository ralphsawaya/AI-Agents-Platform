"""Local MongoDB helper for trip agents.

Connects to the platform's local MongoDB for team_settings lookups
and LLM/key configuration.  All trip domain data (including search
progress and seed status) lives on Atlas — see atlas.py.
"""

from pymongo import MongoClient
from pymongo.collection import Collection

from shared.config import (
    AGENT_ID, MONGODB_URI, MONGODB_DB, LLM_PROVIDER, LLM_MODEL,
    GEMINI_API_KEY, ANTHROPIC_API_KEY, DEEPSEEK_API_KEY,
    GROQ_API_KEY, OPENAI_API_KEY,
    VOYAGE_AI_API_KEY, ATLAS_MONGODB_URI,
)

_ENV_API_KEYS = {
    "gemini": GEMINI_API_KEY,
    "claude": ANTHROPIC_API_KEY,
    "deepseek": DEEPSEEK_API_KEY,
    "groq": GROQ_API_KEY,
    "openai": OPENAI_API_KEY,
}

_client: MongoClient | None = None


def _get_db():
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI)
    return _client[MONGODB_DB]


def get_collection(name: str) -> Collection:
    return _get_db()[name]


def get_team_settings() -> Collection:
    return get_collection("team_settings")


def load_llm_config() -> tuple[str, str, str]:
    """Return (provider, model, api_key) from team_settings, env fallback."""
    if AGENT_ID:
        ts_doc = get_team_settings().find_one({"_id": AGENT_ID})
        if ts_doc:
            provider = ts_doc.get("llm_provider", LLM_PROVIDER)
            model = ts_doc.get("llm_model", LLM_MODEL)
            stored_keys = ts_doc.get("api_keys", {})
            api_key = stored_keys.get(provider) or _ENV_API_KEYS.get(provider, "")
            return provider, model, api_key
    return LLM_PROVIDER, LLM_MODEL, _ENV_API_KEYS.get(LLM_PROVIDER, "")


def load_voyage_api_key() -> str:
    if AGENT_ID:
        ts_doc = get_team_settings().find_one({"_id": AGENT_ID})
        if ts_doc:
            key = (ts_doc.get("integration_keys") or {}).get("VOYAGE_AI_API_KEY")
            if key:
                return key
    return VOYAGE_AI_API_KEY


def load_atlas_uri() -> str:
    if AGENT_ID:
        ts_doc = get_team_settings().find_one({"_id": AGENT_ID})
        if ts_doc:
            uri = (ts_doc.get("integration_keys") or {}).get("ATLAS_MONGODB_URI")
            if uri:
                return uri
    return ATLAS_MONGODB_URI
