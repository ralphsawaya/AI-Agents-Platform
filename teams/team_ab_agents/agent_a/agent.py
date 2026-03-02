"""LangGraph StateGraph definition for AgentA (Summarizer).

Receives text input, summarises it via Gemini, and stores the result in MongoDB.
Graph: input_node -> summarize_node -> output_node
"""

from langgraph.graph import StateGraph, END

from agent_a.state import AgentAState
from agent_a.nodes.input_node import input_node
from agent_a.nodes.summarize_node import summarize_node
from agent_a.nodes.output_node import output_node


def build_agent_a_graph() -> StateGraph:
    graph = StateGraph(AgentAState)

    graph.add_node("input_node", input_node)
    graph.add_node("summarize_node", summarize_node)
    graph.add_node("output_node", output_node)

    graph.set_entry_point("input_node")
    graph.add_edge("input_node", "summarize_node")
    graph.add_edge("summarize_node", "output_node")
    graph.add_edge("output_node", END)

    return graph.compile()
