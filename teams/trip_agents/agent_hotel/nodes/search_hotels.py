"""Search for hotels using MongoDB Atlas $vectorSearch."""

from shared.atlas import get_hotels, vector_search
from shared.logger import get_logger

logger = get_logger("hotel.search")


def search_hotels(state: dict) -> dict:
    embedding = state.get("query_embedding", [])
    if not embedding:
        logger.error("No embedding available for hotel search")
        return {"status": "error"}
    filters = state.get("filters", {})
    logger.info("Running $vectorSearch on trip_hotels (filters: %s)", filters or "none")
    try:
        results = vector_search(get_hotels(), embedding, limit=3, filters=filters)
        logger.info("Found %d hotel results", len(results))
        for i, r in enumerate(results):
            logger.info("  #%d: %s — %d* — EUR%.0f/night (score: %.4f)",
                         i + 1, r.get("name", ""), r.get("stars", 0),
                         r.get("price_per_night_eur", 0), r.get("score", 0))
        return {"results": results, "status": "complete"}
    except Exception as exc:
        logger.error("Hotel search failed: %s", exc)
        return {"results": [], "status": "error"}
