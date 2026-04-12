"""Search tools for the Flight Search agent."""

from langchain_core.tools import tool
from shared.atlas import get_flights, vector_search
from shared.voyage import embed_query


@tool
def search_flights_by_text(query: str, limit: int = 3) -> list[dict]:
    """Search for flights matching a natural-language description."""
    return vector_search(get_flights(), embed_query(query), limit=limit)
