"""MongoDB helper for trading agents."""

from pymongo import MongoClient
from pymongo.collection import Collection

from shared.config import MONGODB_URI, MONGODB_DB

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
