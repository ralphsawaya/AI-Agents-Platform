"""LangGraph StateGraph definition for the Hotel Search agent."""

from agent_hotel.state import HotelSearchState
from shared.atlas import get_hotels
from shared.nodes.search_nodes import make_embed_node, make_vector_search_node
from shared.search_graph import build_embed_search_graph

_embed = make_embed_node("hotel")
_search = make_vector_search_node(
    get_hotels,
    "hotel",
    "trip_hotels",
    format_hit=lambda _i, r: (
        f"{r.get('name', '')} — {r.get('stars', 0)}* — "
        f"EUR{r.get('price_per_night_eur', 0)}/night (score: {r.get('score', 0):.4f})"
    ),
)


def build_hotel_graph():
    return build_embed_search_graph(HotelSearchState, _embed, _search, "search_hotels")
