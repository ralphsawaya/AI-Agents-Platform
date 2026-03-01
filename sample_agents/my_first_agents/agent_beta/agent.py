"""LangGraph StateGraph definition for agent_beta (Report Generator).

Receives a summary from agent_alpha and generates a structured
markdown report.
Graph: input_node -> report_node -> output_node
"""

from langgraph.graph import StateGraph, END

from agent_beta.state import BetaState
from agent_beta.nodes.input_node import input_node
from agent_beta.nodes.report_node import report_node
from agent_beta.nodes.output_node import output_node


def build_beta_graph() -> StateGraph:
    graph = StateGraph(BetaState)

    graph.add_node("input_node", input_node)
    graph.add_node("report_node", report_node)
    graph.add_node("output_node", output_node)

    graph.set_entry_point("input_node")
    graph.add_edge("input_node", "report_node")
    graph.add_edge("report_node", "output_node")
    graph.add_edge("output_node", END)

    return graph.compile()
