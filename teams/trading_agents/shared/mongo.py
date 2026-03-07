"""MongoDB helper for trading agents."""

from pymongo import MongoClient
from pymongo.collection import Collection

from shared.config import (
    MONGODB_URI, MONGODB_DB, LLM_PROVIDER, LLM_MODEL,
    GEMINI_API_KEY, ANTHROPIC_API_KEY, DEEPSEEK_API_KEY,
    RISK_DEFAULTS, INDICATOR_DEFAULTS,
)

_ENV_API_KEYS = {
    "gemini": GEMINI_API_KEY,
    "claude": ANTHROPIC_API_KEY,
    "deepseek": DEEPSEEK_API_KEY,
}

_client: MongoClient | None = None


def _get_db():
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI)
    return _client[MONGODB_DB]


def get_collection(name: str) -> Collection:
    """Return a named MongoDB collection."""
    return _get_db()[name]


def get_market_regimes() -> Collection:
    return get_collection("market_regimes")


def get_strategy_selections() -> Collection:
    return get_collection("strategy_selections")


def get_trade_signals() -> Collection:
    return get_collection("trade_signals")


def get_trades() -> Collection:
    return get_collection("trades")


def get_risk_state() -> Collection:
    return get_collection("risk_state")


def get_trading_config() -> Collection:
    return get_collection("trading_config")


# ----- Config loaders (read from MongoDB, fall back to env/defaults) -----

def load_llm_config() -> tuple[str, str, str]:
    """Return (provider, model, api_key) from the stored trading config.

    API keys stored in MongoDB take precedence over environment variables.
    """
    doc = get_trading_config().find_one(sort=[("updated_at", -1)])
    if doc:
        provider = doc.get("llm_provider", LLM_PROVIDER)
        model = doc.get("llm_model", LLM_MODEL)
        stored_keys = doc.get("api_keys", {})
        api_key = stored_keys.get(provider) or _ENV_API_KEYS.get(provider, "")
        return provider, model, api_key
    env_key = _ENV_API_KEYS.get(LLM_PROVIDER, "")
    return LLM_PROVIDER, LLM_MODEL, env_key


def load_risk_config() -> dict:
    """Return risk defaults from the stored trading config."""
    doc = get_trading_config().find_one(sort=[("updated_at", -1)])
    if doc and "risk_defaults" in doc:
        merged = dict(RISK_DEFAULTS)
        merged.update(doc["risk_defaults"])
        return merged
    return dict(RISK_DEFAULTS)


def load_indicator_config() -> dict:
    """Return indicator periods from the stored trading config."""
    doc = get_trading_config().find_one(sort=[("updated_at", -1)])
    if doc and "indicator_periods" in doc:
        merged = dict(INDICATOR_DEFAULTS)
        merged.update(doc["indicator_periods"])
        return merged
    return dict(INDICATOR_DEFAULTS)
