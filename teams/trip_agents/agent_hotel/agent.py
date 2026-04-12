"""LangGraph StateGraph definition for the Hotel Search agent.

Graph: embed_query -> search_hotels -> END
"""

from langgraph.graph import StateGraph, END

from agent_hotel.state import HotelSearchState
from agent_hotel.nodes.embed_query import embed_query
from agent_hotel.nodes.search_hotels import search_hotels


def build_hotel_graph():
    graph = StateGraph(HotelSearchState)
    graph.add_node("embed_query", embed_query)
    graph.add_node("search_hotels", search_hotels)
    graph.set_entry_point("embed_query")
    graph.add_edge("embed_query", "search_hotels")
    graph.add_edge("search_hotels", END)
    return graph.compile()
