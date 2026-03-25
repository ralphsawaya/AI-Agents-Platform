"""LangGraph StateGraph definition for the Voice Caller agent.

Graph: fetch_qualified_leads -> initiate_calls -> record_outcomes -> END
"""

from langgraph.graph import StateGraph, END

from agent_voice_caller.state import VoiceCallerState
from agent_voice_caller.nodes.fetch_qualified_leads import fetch_qualified_leads
from agent_voice_caller.nodes.initiate_calls import initiate_calls
from agent_voice_caller.nodes.record_outcomes import record_outcomes


def build_voice_caller_graph() -> StateGraph:
    graph = StateGraph(VoiceCallerState)

    graph.add_node("fetch_qualified_leads", fetch_qualified_leads)
    graph.add_node("initiate_calls", initiate_calls)
    graph.add_node("record_outcomes", record_outcomes)

    graph.set_entry_point("fetch_qualified_leads")
    graph.add_edge("fetch_qualified_leads", "initiate_calls")
    graph.add_edge("initiate_calls", "record_outcomes")
    graph.add_edge("record_outcomes", END)

    return graph.compile()
