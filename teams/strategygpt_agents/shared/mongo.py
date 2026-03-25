"""MongoDB helper for StrategyGPT agents."""

from pymongo import MongoClient

from shared.config import (
    AGENT_ID, MONGODB_URI, MONGODB_DB,
    LLM_PROVIDER, LLM_MODEL,
    GROQ_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY, DEEPSEEK_API_KEY,
    OPENAI_API_KEY,
)

_ENV_API_KEYS = {
    "groq": GROQ_API_KEY,
    "gemini": GEMINI_API_KEY,
    "claude": ANTHROPIC_API_KEY,
    "deepseek": DEEPSEEK_API_KEY,
    "openai": OPENAI_API_KEY,
}

_client: MongoClient | None = None


def _get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI)
    return _client


def get_leads_collection():
    """Return the strategygpt_leads collection."""
    return _get_client()[MONGODB_DB]["strategygpt_leads"]


def get_calls_collection():
    """Return the strategygpt_calls collection."""
    return _get_client()[MONGODB_DB]["strategygpt_calls"]


def get_dnc_collection():
    """Return the strategygpt_dnc (Do Not Call) collection."""
    return _get_client()[MONGODB_DB]["strategygpt_dnc"]


def load_llm_config() -> tuple[str, str, str]:
    """Return (provider, model, api_key) from team_settings in MongoDB.

    Falls back to environment variables if no settings are stored.
    """
    if AGENT_ID:
        doc = _get_client()[MONGODB_DB]["team_settings"].find_one({"_id": AGENT_ID})
        if doc:
            provider = doc.get("llm_provider", LLM_PROVIDER)
            model = doc.get("llm_model", LLM_MODEL)
            stored_keys = doc.get("api_keys", {})
            api_key = stored_keys.get(provider) or _ENV_API_KEYS.get(provider, "")
            return provider, model, api_key
    env_key = _ENV_API_KEYS.get(LLM_PROVIDER, "")
    return LLM_PROVIDER, LLM_MODEL, env_key
