"""Search for flights using MongoDB Atlas $vectorSearch."""

from shared.atlas import get_flights, vector_search
from shared.logger import get_logger

logger = get_logger("flight.search")


def search_flights(state: dict) -> dict:
    embedding = state.get("query_embedding", [])
    if not embedding:
        logger.error("No embedding available for flight search")
        return {"status": "error"}
    filters = state.get("filters", {})
    logger.info("Running $vectorSearch on trip_flights (filters: %s)", filters or "none")
    try:
        results = vector_search(get_flights(), embedding, limit=3, filters=filters)
        logger.info("Found %d flight results", len(results))
        for i, r in enumerate(results):
            logger.info("  #%d: %s %s — €%.0f (score: %.4f)",
                         i + 1, r.get("airline", ""), r.get("flight_number", ""),
                         r.get("price_eur", 0), r.get("score", 0))
        return {"results": results, "status": "complete"}
    except Exception as exc:
        logger.error("Flight search failed: %s", exc)
        return {"results": [], "status": "error"}
