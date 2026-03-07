"""LangGraph StateGraph definition for the Risk Manager agent.

Graph: fetch_account -> calculate_risk -> approve_trade -> END
"""

from langgraph.graph import StateGraph, END

from agent_risk_manager.state import RiskManagerState
from agent_risk_manager.nodes.fetch_account import fetch_account
from agent_risk_manager.nodes.calculate_risk import calculate_risk
from agent_risk_manager.nodes.approve_trade import approve_trade


def build_risk_manager_graph() -> StateGraph:
    graph = StateGraph(RiskManagerState)

    graph.add_node("fetch_account", fetch_account)
    graph.add_node("calculate_risk", calculate_risk)
    graph.add_node("approve_trade", approve_trade)

    graph.set_entry_point("fetch_account")
    graph.add_edge("fetch_account", "calculate_risk")
    graph.add_edge("calculate_risk", "approve_trade")
    graph.add_edge("approve_trade", END)

    return graph.compile()
