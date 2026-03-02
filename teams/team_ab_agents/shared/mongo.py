"""MongoDB helper for TeamAB agents."""

from pymongo import MongoClient

from shared.config import MONGODB_URI, MONGODB_DB, MONGODB_COLLECTION

_client: MongoClient | None = None


def get_collection():
    """Return the TeamAB MongoDB collection, reusing the client."""
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI)
    return _client[MONGODB_DB][MONGODB_COLLECTION]


def get_next_text_id() -> int:
    """Return the next available text_id (auto-increment)."""
    col = get_collection()
    last = col.find_one(sort=[("text_id", -1)])
    return (last["text_id"] + 1) if last else 1
