"""Orchestrator supervisor — monitors agent execution health."""

from shared.logger import get_logger

logger = get_logger("orchestrator.supervisor")


def check_agent_health(state: dict) -> bool:
    """Verify the current state is healthy before proceeding."""
    if state.get("status") == "error":
        logger.error("Agent reported error state")
        return False
    return True
