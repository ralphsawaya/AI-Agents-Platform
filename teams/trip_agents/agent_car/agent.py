"""LangGraph StateGraph definition for the Car Search agent."""

from agent_car.state import CarSearchState
from shared.atlas import get_cars
from shared.nodes.search_nodes import make_embed_node, make_vector_search_node
from shared.search_graph import build_embed_search_graph

_embed = make_embed_node("car")
_search = make_vector_search_node(
    get_cars,
    "car",
    "trip_cars",
    format_hit=lambda _i, r: (
        f"{r.get('color', '')} {r.get('make', '')} {r.get('model', '')} — "
        f"EUR{r.get('price_per_day_eur', 0)}/day (score: {r.get('score', 0):.4f})"
    ),
)


def build_car_graph():
    return build_embed_search_graph(CarSearchState, _embed, _search, "search_cars")
