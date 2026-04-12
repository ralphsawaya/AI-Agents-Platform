"""LangGraph StateGraph definition for the Car Rental Search agent.

Graph: embed_query -> search_cars -> END
"""

from langgraph.graph import StateGraph, END

from agent_car.state import CarSearchState
from agent_car.nodes.embed_query import embed_query
from agent_car.nodes.search_cars import search_cars


def build_car_graph():
    graph = StateGraph(CarSearchState)
    graph.add_node("embed_query", embed_query)
    graph.add_node("search_cars", search_cars)
    graph.set_entry_point("embed_query")
    graph.add_edge("embed_query", "search_cars")
    graph.add_edge("search_cars", END)
    return graph.compile()
