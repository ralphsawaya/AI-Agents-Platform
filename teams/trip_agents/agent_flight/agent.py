"""LangGraph StateGraph definition for the Flight Search agent."""

from agent_flight.state import FlightSearchState
from shared.atlas import get_flights
from shared.nodes.search_nodes import make_embed_node, make_vector_search_node
from shared.search_graph import build_embed_search_graph

_embed = make_embed_node("flight")
_search = make_vector_search_node(
    get_flights,
    "flight",
    "trip_flights",
    format_hit=lambda _i, r: (
        f"{r.get('airline', '')} {r.get('flight_number', '')} — "
        f"EUR{r.get('price_eur', 0)} (score: {r.get('score', 0):.4f})"
    ),
)


def build_flight_graph():
    return build_embed_search_graph(FlightSearchState, _embed, _search, "search_flights")
