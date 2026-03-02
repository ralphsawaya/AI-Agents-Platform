"""Master LangGraph wiring agent_alpha -> agent_beta in sequence.

This graph demonstrates a simple pipeline where:
1. agent_alpha summarises the input text
2. agent_beta generates a structured report from the summary
"""

from langgraph.graph import StateGraph, END

from orchestrator.state import OrchestratorState
from agent_alpha.agent import build_alpha_graph
from agent_beta.agent import build_beta_graph
from shared.logger import get_logger

logger = get_logger("orchestrator.graph")


def run_alpha(state: dict) -> dict:
    """Execute agent_alpha's summarisation graph."""
    logger.info("Orchestrator: running agent_alpha")
    alpha_graph = build_alpha_graph()
    result = alpha_graph.invoke({
        "input_text": state["input_text"],
        "summary": "",
        "word_count": 0,
        "status": "pending",
    })
    return {
        "summary": result["summary"],
        "current_agent": "agent_alpha",
        "status": "alpha_complete",
    }


def run_beta(state: dict) -> dict:
    """Execute agent_beta's report generation graph."""
    logger.info("Orchestrator: running agent_beta")
    beta_graph = build_beta_graph()
    result = beta_graph.invoke({
        "summary": state["summary"],
        "report": "",
        "title": "",
        "status": "pending",
    })
    return {
        "report": result["report"],
        "current_agent": "agent_beta",
        "status": "complete",
    }


def build_orchestrator_graph():
    graph = StateGraph(OrchestratorState)

    graph.add_node("agent_alpha", run_alpha)
    graph.add_node("agent_beta", run_beta)

    graph.set_entry_point("agent_alpha")
    graph.add_edge("agent_alpha", "agent_beta")
    graph.add_edge("agent_beta", END)

    return graph.compile()
