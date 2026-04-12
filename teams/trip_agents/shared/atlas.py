"""Atlas MongoDB client for trip domain collections.

trip_flights, trip_hotels, trip_cars, and trip_reservations live on
MongoDB Atlas and are accessed through this module.
"""

import certifi
from pymongo import MongoClient
from pymongo.collection import Collection

from shared.config import (
    FLIGHTS_COLLECTION, HOTELS_COLLECTION,
    CARS_COLLECTION, RESERVATIONS_COLLECTION,
    CHAT_COLLECTION, LONG_MEMORY_COLLECTION,
)
from shared.mongo import load_atlas_uri
from shared.logger import get_logger

logger = get_logger("shared.atlas")

_atlas_client: MongoClient | None = None


def _get_atlas_db():
    global _atlas_client
    uri = load_atlas_uri()
    if not uri:
        raise ValueError(
            "ATLAS_MONGODB_URI is not configured. "
            "Set it in the Settings tab or as an environment variable."
        )
    if _atlas_client is None:
        _atlas_client = MongoClient(uri, tlsCAFile=certifi.where())
    return _atlas_client.get_default_database(default="trip_data")


def get_atlas_collection(name: str) -> Collection:
    return _get_atlas_db()[name]


def get_flights() -> Collection:
    return get_atlas_collection(FLIGHTS_COLLECTION)


def get_hotels() -> Collection:
    return get_atlas_collection(HOTELS_COLLECTION)


def get_cars() -> Collection:
    return get_atlas_collection(CARS_COLLECTION)


def get_reservations() -> Collection:
    return get_atlas_collection(RESERVATIONS_COLLECTION)


def get_chat_persistence() -> Collection:
    return get_atlas_collection(CHAT_COLLECTION)


def get_long_memory() -> Collection:
    return get_atlas_collection(LONG_MEMORY_COLLECTION)


def vector_search(collection: Collection, query_vector: list[float],
                   limit: int = 3, num_candidates: int = 100,
                   index_name: str = "vector_index",
                   filters: dict | None = None) -> list[dict]:
    """Run a $vectorSearch aggregation with optional pre-filters."""
    vs_stage: dict = {
        "index": index_name,
        "path": "embedded_description",
        "queryVector": query_vector,
        "numCandidates": num_candidates,
        "limit": limit,
    }
    if filters:
        mongo_filter = _build_filter(filters)
        if mongo_filter:
            vs_stage["filter"] = mongo_filter
            logger.info("Applying pre-filter on %s: %s", collection.name, mongo_filter)

    pipeline = [
        {"$vectorSearch": vs_stage},
        {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
        {"$project": {"embedded_description": 0}},
    ]
    results = list(collection.aggregate(pipeline))
    for r in results:
        r["_id"] = str(r["_id"])
    return results


def _build_filter(filters: dict) -> dict | None:
    """Convert a flat filter dict into a $vectorSearch MQL filter expression."""
    clauses = []
    for field, value in filters.items():
        if field == "stars" and isinstance(value, (int, float)):
            clauses.append({field: {"$gte": value}})
        elif isinstance(value, str):
            clauses.append({field: {"$eq": value}})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}
