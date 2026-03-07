"""LangGraph StateGraph definition for the Analyst agent.

Graph: fetch_data -> compute_indicators -> classify_regime -> END
"""

from langgraph.graph import StateGraph, END

from agent_analyst.state import AnalystState
from agent_analyst.nodes.fetch_data import fetch_data
from agent_analyst.nodes.compute_indicators import compute_indicators
from agent_analyst.nodes.classify_regime import classify_regime


def build_analyst_graph() -> StateGraph:
    graph = StateGraph(AnalystState)

    graph.add_node("fetch_data", fetch_data)
    graph.add_node("compute_indicators", compute_indicators)
    graph.add_node("classify_regime", classify_regime)

    graph.set_entry_point("fetch_data")
    graph.add_edge("fetch_data", "compute_indicators")
    graph.add_edge("compute_indicators", "classify_regime")
    graph.add_edge("classify_regime", END)

    return graph.compile()
