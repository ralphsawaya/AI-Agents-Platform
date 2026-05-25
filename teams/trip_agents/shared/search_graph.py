"""Shared LangGraph builder for embed → vector-search sub-agents."""

from collections.abc import Callable

from langgraph.graph import END, StateGraph


def build_embed_search_graph(
    state_class: type,
    embed_node: Callable,
    search_node: Callable,
    search_node_name: str,
):
    """Graph: embed_query --(ok)--> search --> END; embed error --> END."""

    def _route_after_embed(state: dict) -> str:
        if state.get("status") == "error":
            return END
        return search_node_name

    graph = StateGraph(state_class)
    graph.add_node("embed_query", embed_node)
    graph.add_node(search_node_name, search_node)
    graph.set_entry_point("embed_query")
    graph.add_conditional_edges(
        "embed_query",
        _route_after_embed,
        {END: END, search_node_name: search_node_name},
    )
    graph.add_edge(search_node_name, END)
    return graph.compile()
