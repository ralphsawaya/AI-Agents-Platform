"""LangGraph StateGraph definition for the Strategist agent.

Graph: evaluate_strategies -> select_strategy -> update_selection -> END
"""

from langgraph.graph import StateGraph, END

from agent_strategist.state import StrategistState
from agent_strategist.nodes.evaluate_strategies import evaluate_strategies
from agent_strategist.nodes.select_strategy import select_strategy
from agent_strategist.nodes.update_selection import update_selection


def build_strategist_graph() -> StateGraph:
    graph = StateGraph(StrategistState)

    graph.add_node("evaluate_strategies", evaluate_strategies)
    graph.add_node("select_strategy", select_strategy)
    graph.add_node("update_selection", update_selection)

    graph.set_entry_point("evaluate_strategies")
    graph.add_edge("evaluate_strategies", "select_strategy")
    graph.add_edge("select_strategy", "update_selection")
    graph.add_edge("update_selection", END)

    return graph.compile()
