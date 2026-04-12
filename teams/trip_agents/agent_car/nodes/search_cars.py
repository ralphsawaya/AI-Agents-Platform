"""Search for rental cars using MongoDB Atlas $vectorSearch."""

from shared.atlas import get_cars, vector_search
from shared.logger import get_logger

logger = get_logger("car.search")


def search_cars(state: dict) -> dict:
    embedding = state.get("query_embedding", [])
    if not embedding:
        logger.error("No embedding available for car rental search")
        return {"status": "error"}
    filters = state.get("filters", {})
    logger.info("Running $vectorSearch on trip_cars (filters: %s)", filters or "none")
    try:
        results = vector_search(get_cars(), embedding, limit=3, filters=filters)
        logger.info("Found %d car rental results", len(results))
        for i, r in enumerate(results):
            logger.info("  #%d: %s %s %s — EUR%.0f/day (score: %.4f)",
                         i + 1, r.get("color", ""), r.get("make", ""),
                         r.get("model", ""), r.get("price_per_day_eur", 0),
                         r.get("score", 0))
        return {"results": results, "status": "complete"}
    except Exception as exc:
        logger.error("Car rental search failed: %s", exc)
        return {"results": [], "status": "error"}
