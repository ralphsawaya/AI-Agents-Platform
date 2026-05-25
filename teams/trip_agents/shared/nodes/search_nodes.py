"""Factory functions for embed + vector-search LangGraph nodes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from shared.atlas import vector_search
from shared.logger import get_logger
from shared.voyage import embed_query as voyage_embed


def make_embed_node(agent_label: str) -> Callable[[dict], dict]:
    """Return a LangGraph node that embeds the query via Voyage AI."""
    log = get_logger(f"{agent_label}.embed_query")

    def embed_query(state: dict) -> dict:
        query = state.get("query", "")
        if not query:
            log.error("No query provided for %s search", agent_label)
            return {"status": "error"}
        log.info("Embedding %s query: %s", agent_label, query[:100])
        try:
            embedding = voyage_embed(query)
            log.info("Generated embedding with %d dimensions", len(embedding))
            return {"query_embedding": embedding, "status": "embedded"}
        except Exception as exc:
            log.error("Failed to embed query: %s", exc)
            return {"status": "error"}

    return embed_query


def make_vector_search_node(
    collection_getter: Callable[[], Any],
    agent_label: str,
    collection_name: str,
    format_hit: Callable[[int, dict], str] | None = None,
) -> Callable[[dict], dict]:
    """Return a LangGraph node that runs $vectorSearch on a trip collection."""
    log = get_logger(f"{agent_label}.search")

    def search(state: dict) -> dict:
        embedding = state.get("query_embedding", [])
        if not embedding:
            log.error("No embedding available for %s search", agent_label)
            return {"status": "error"}
        filters = state.get("filters", {})
        log.info("Running $vectorSearch on %s (filters: %s)", collection_name, filters or "none")
        try:
            results = vector_search(collection_getter(), embedding, limit=3, filters=filters)
            log.info("Found %d %s results", len(results), agent_label)
            for i, row in enumerate(results):
                if format_hit:
                    log.info("  #%d: %s", i + 1, format_hit(i, row))
            return {"results": results, "status": "complete"}
        except Exception as exc:
            log.error("%s search failed: %s", agent_label.capitalize(), exc)
            return {"results": [], "status": "error"}

    return search
