"""LangGraph StateGraph definition for AgentB (Title Writer).

Receives a summary from AgentA, generates a title via Gemini,
and stores the result in MongoDB.
Graph: input_node -> title_node -> output_node
"""

from langgraph.graph import StateGraph, END

from agent_b.state import AgentBState
from agent_b.nodes.input_node import input_node
from agent_b.nodes.title_node import title_node
from agent_b.nodes.output_node import output_node


def build_agent_b_graph() -> StateGraph:
    graph = StateGraph(AgentBState)

    graph.add_node("input_node", input_node)
    graph.add_node("title_node", title_node)
    graph.add_node("output_node", output_node)

    graph.set_entry_point("input_node")
    graph.add_edge("input_node", "title_node")
    graph.add_edge("title_node", "output_node")
    graph.add_edge("output_node", END)

    return graph.compile()
