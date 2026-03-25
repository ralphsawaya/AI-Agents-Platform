"""LangGraph StateGraph definition for the Lead Sourcer agent.

Graph: search_places -> filter_leads -> store_leads -> END
"""

from langgraph.graph import StateGraph, END

from agent_lead_sourcer.state import LeadSourcerState
from agent_lead_sourcer.nodes.search_places import search_places
from agent_lead_sourcer.nodes.filter_leads import filter_leads
from agent_lead_sourcer.nodes.store_leads import store_leads


def build_lead_sourcer_graph() -> StateGraph:
    graph = StateGraph(LeadSourcerState)

    graph.add_node("search_places", search_places)
    graph.add_node("filter_leads", filter_leads)
    graph.add_node("store_leads", store_leads)

    graph.set_entry_point("search_places")
    graph.add_edge("search_places", "filter_leads")
    graph.add_edge("filter_leads", "store_leads")
    graph.add_edge("store_leads", END)

    return graph.compile()
