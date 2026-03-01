"""LangGraph StateGraph definition for agent_alpha (Summarizer).

Receives text input and produces a concise summary using an LLM.
Graph: input_node -> summarize_node -> output_node
"""

from langgraph.graph import StateGraph, END

from agent_alpha.state import AlphaState
from agent_alpha.nodes.input_node import input_node
from agent_alpha.nodes.summarize_node import summarize_node
from agent_alpha.nodes.output_node import output_node


def build_alpha_graph() -> StateGraph:
    graph = StateGraph(AlphaState)

    graph.add_node("input_node", input_node)
    graph.add_node("summarize_node", summarize_node)
    graph.add_node("output_node", output_node)

    graph.set_entry_point("input_node")
    graph.add_edge("input_node", "summarize_node")
    graph.add_edge("summarize_node", "output_node")
    graph.add_edge("output_node", END)

    return graph.compile()
