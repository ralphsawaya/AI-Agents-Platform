"""Master LangGraph wiring AgentA -> AgentB in sequence.

Pipeline:
1. AgentA summarises the input text and stores it in MongoDB
2. AgentB generates a title from the summary and stores it in MongoDB
"""

from langgraph.graph import StateGraph, END

from orchestrator.state import OrchestratorState
from agent_a.agent import build_agent_a_graph
from agent_b.agent import build_agent_b_graph
from shared.logger import get_logger

logger = get_logger("orchestrator.graph")


def run_agent_a(state: dict) -> dict:
    """Execute AgentA's summarisation graph."""
    logger.info("Orchestrator: running AgentA")
    agent_a_graph = build_agent_a_graph()
    result = agent_a_graph.invoke({
        "input_text": state["input_text"],
        "summary": "",
        "text_id": 0,
        "word_count": 0,
        "status": "pending",
    })
    return {
        "summary": result["summary"],
        "text_id": result["text_id"],
        "current_agent": "agent_a",
        "status": "agent_a_complete",
    }


def run_agent_b(state: dict) -> dict:
    """Execute AgentB's title generation graph."""
    logger.info("Orchestrator: running AgentB")
    agent_b_graph = build_agent_b_graph()
    result = agent_b_graph.invoke({
        "summary": state["summary"],
        "title": "",
        "text_id": state["text_id"],
        "status": "pending",
    })
    return {
        "title": result["title"],
        "current_agent": "agent_b",
        "status": "complete",
    }


def build_orchestrator_graph():
    graph = StateGraph(OrchestratorState)

    graph.add_node("agent_a", run_agent_a)
    graph.add_node("agent_b", run_agent_b)

    graph.set_entry_point("agent_a")
    graph.add_edge("agent_a", "agent_b")
    graph.add_edge("agent_b", END)

    return graph.compile()
