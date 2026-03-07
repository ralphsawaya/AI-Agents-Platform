"""LangGraph StateGraph definition for the Executor agent.

Graph: validate_signal -> place_order -> confirm_order -> set_stop_loss -> END
"""

from langgraph.graph import StateGraph, END

from agent_executor.state import ExecutorState
from agent_executor.nodes.validate_signal import validate_signal
from agent_executor.nodes.place_order import place_order
from agent_executor.nodes.confirm_order import confirm_order
from agent_executor.nodes.set_stop_loss import set_stop_loss


def build_executor_graph() -> StateGraph:
    graph = StateGraph(ExecutorState)

    graph.add_node("validate_signal", validate_signal)
    graph.add_node("place_order", place_order)
    graph.add_node("confirm_order", confirm_order)
    graph.add_node("set_stop_loss", set_stop_loss)

    graph.set_entry_point("validate_signal")
    graph.add_edge("validate_signal", "place_order")
    graph.add_edge("place_order", "confirm_order")
    graph.add_edge("confirm_order", "set_stop_loss")
    graph.add_edge("set_stop_loss", END)

    return graph.compile()
