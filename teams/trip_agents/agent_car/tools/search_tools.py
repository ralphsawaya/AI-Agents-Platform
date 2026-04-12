"""Search tools for the Car Rental Search agent."""

from langchain_core.tools import tool
from shared.atlas import get_cars, vector_search
from shared.voyage import embed_query


@tool
def search_cars_by_text(query: str, limit: int = 3) -> list[dict]:
    """Search for rental cars matching a natural-language description."""
    return vector_search(get_cars(), embed_query(query), limit=limit)
