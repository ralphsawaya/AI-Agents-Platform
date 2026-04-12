"""LangGraph StateGraph definition for the Flight Search agent.

Graph: embed_query -> search_flights -> END
"""

from langgraph.graph import StateGraph, END

from agent_flight.state import FlightSearchState
from agent_flight.nodes.embed_query import embed_query
from agent_flight.nodes.search_flights import search_flights


def build_flight_graph():
    graph = StateGraph(FlightSearchState)
    graph.add_node("embed_query", embed_query)
    graph.add_node("search_flights", search_flights)
    graph.set_entry_point("embed_query")
    graph.add_edge("embed_query", "search_flights")
    graph.add_edge("search_flights", END)
    return graph.compile()
