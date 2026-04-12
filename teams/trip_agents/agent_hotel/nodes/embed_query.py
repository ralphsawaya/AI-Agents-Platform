"""Embed the hotel search query using Voyage AI."""

from shared.voyage import embed_query as voyage_embed
from shared.logger import get_logger

logger = get_logger("hotel.embed_query")


def embed_query(state: dict) -> dict:
    query = state.get("query", "")
    if not query:
        logger.error("No query provided for hotel search")
        return {"status": "error"}
    logger.info("Embedding hotel query: %s", query[:100])
    try:
        embedding = voyage_embed(query)
        logger.info("Generated embedding with %d dimensions", len(embedding))
        return {"query_embedding": embedding, "status": "embedded"}
    except Exception as exc:
        logger.error("Failed to embed query: %s", exc)
        return {"status": "error"}
