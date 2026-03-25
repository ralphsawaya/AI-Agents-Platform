"""Orchestrator graphs for StrategyGPT.

Three modes:
  - sourcing: lead_sourcer -> lead_qualifier -> END
  - outreach: voice_caller -> END
  - full: lead_sourcer -> lead_qualifier -> voice_caller -> END
"""

from langgraph.graph import StateGraph, END

from orchestrator.state import SourcingPipelineState, OutreachPipelineState, FullPipelineState
from agent_lead_sourcer.agent import build_lead_sourcer_graph
from agent_lead_qualifier.agent import build_lead_qualifier_graph
from agent_voice_caller.agent import build_voice_caller_graph
from shared.logger import get_logger

logger = get_logger("orchestrator.graph")


# -- Sourcing pipeline nodes --------------------------------------------------

def run_lead_sourcer(state: dict) -> dict:
    """Execute the Lead Sourcer agent's Google Maps search."""
    logger.info("Orchestrator: running Lead Sourcer")
    graph = build_lead_sourcer_graph()
    result = graph.invoke({
        "city": state["city"],
        "categories": state["categories"],
        "min_reviews": state["min_reviews"],
        "min_rating": state["min_rating"],
        "max_leads": state["max_leads"],
        "raw_places": [],
        "filtered_leads": [],
        "stored_count": 0,
        "status": "pending",
    })
    return {
        "raw_places": result.get("raw_places", []),
        "filtered_leads": result.get("filtered_leads", []),
        "stored_count": result.get("stored_count", 0),
        "current_agent": "lead_sourcer",
        "status": result.get("status", ""),
    }


def run_lead_qualifier(state: dict) -> dict:
    """Execute the Lead Qualifier agent's enrichment and script generation."""
    logger.info("Orchestrator: running Lead Qualifier")
    graph = build_lead_qualifier_graph()
    result = graph.invoke({
        "new_leads": [],
        "qualified_leads": [],
        "invalid_leads": [],
        "qualified_count": 0,
        "scripts_generated": 0,
        "status": "pending",
    })
    return {
        "qualified_count": result.get("qualified_count", 0),
        "scripts_generated": result.get("scripts_generated", 0),
        "current_agent": "lead_qualifier",
        "status": result.get("status", ""),
    }


# -- Outreach pipeline nodes --------------------------------------------------

def run_voice_caller(state: dict) -> dict:
    """Execute the Voice Caller agent's outreach calls."""
    logger.info("Orchestrator: running Voice Caller")
    graph = build_voice_caller_graph()
    result = graph.invoke({
        "batch_size": state.get("batch_size", 20),
        "leads_to_call": [],
        "call_results": [],
        "interested_count": 0,
        "not_interested_count": 0,
        "no_answer_count": 0,
        "status": "pending",
    })
    return {
        "leads_to_call": result.get("leads_to_call", []),
        "call_results": result.get("call_results", []),
        "interested_count": result.get("interested_count", 0),
        "not_interested_count": result.get("not_interested_count", 0),
        "no_answer_count": result.get("no_answer_count", 0),
        "current_agent": "voice_caller",
        "status": "complete",
    }


# -- Graph builders ------------------------------------------------------------

def build_sourcing_graph():
    """Build the sourcing pipeline: lead_sourcer -> lead_qualifier -> END"""
    graph = StateGraph(SourcingPipelineState)

    graph.add_node("lead_sourcer", run_lead_sourcer)
    graph.add_node("lead_qualifier", run_lead_qualifier)

    graph.set_entry_point("lead_sourcer")
    graph.add_edge("lead_sourcer", "lead_qualifier")
    graph.add_edge("lead_qualifier", END)

    return graph.compile()


def build_outreach_graph():
    """Build the outreach pipeline: voice_caller -> END"""
    graph = StateGraph(OutreachPipelineState)

    graph.add_node("voice_caller", run_voice_caller)

    graph.set_entry_point("voice_caller")
    graph.add_edge("voice_caller", END)

    return graph.compile()


def build_full_graph():
    """Build the full pipeline: lead_sourcer -> lead_qualifier -> voice_caller -> END"""
    graph = StateGraph(FullPipelineState)

    graph.add_node("lead_sourcer", run_lead_sourcer)
    graph.add_node("lead_qualifier", run_lead_qualifier)
    graph.add_node("voice_caller", run_voice_caller)

    graph.set_entry_point("lead_sourcer")
    graph.add_edge("lead_sourcer", "lead_qualifier")
    graph.add_edge("lead_qualifier", "voice_caller")
    graph.add_edge("voice_caller", END)

    return graph.compile()
