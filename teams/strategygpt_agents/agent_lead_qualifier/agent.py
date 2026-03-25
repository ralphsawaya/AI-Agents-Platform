"""LangGraph StateGraph definition for the Lead Qualifier agent.

Graph: fetch_new_leads -> enrich_leads -> generate_scripts -> END
"""

from langgraph.graph import StateGraph, END

from agent_lead_qualifier.state import LeadQualifierState
from agent_lead_qualifier.nodes.fetch_new_leads import fetch_new_leads
from agent_lead_qualifier.nodes.enrich_leads import enrich_leads
from agent_lead_qualifier.nodes.generate_scripts import generate_scripts


def build_lead_qualifier_graph() -> StateGraph:
    graph = StateGraph(LeadQualifierState)

    graph.add_node("fetch_new_leads", fetch_new_leads)
    graph.add_node("enrich_leads", enrich_leads)
    graph.add_node("generate_scripts", generate_scripts)

    graph.set_entry_point("fetch_new_leads")
    graph.add_edge("fetch_new_leads", "enrich_leads")
    graph.add_edge("enrich_leads", "generate_scripts")
    graph.add_edge("generate_scripts", END)

    return graph.compile()
