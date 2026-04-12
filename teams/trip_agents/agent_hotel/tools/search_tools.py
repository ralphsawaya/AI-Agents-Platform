"""Search tools for the Hotel Search agent."""

from langchain_core.tools import tool
from shared.atlas import get_hotels, vector_search
from shared.voyage import embed_query


@tool
def search_hotels_by_text(query: str, limit: int = 3) -> list[dict]:
    """Search for hotels matching a natural-language description."""
    return vector_search(get_hotels(), embed_query(query), limit=limit)
