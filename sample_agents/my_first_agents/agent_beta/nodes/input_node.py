"""Input node — receives summary from agent_alpha."""

from shared.logger import get_logger

logger = get_logger("agent_beta.input_node")


def input_node(state: dict) -> dict:
    summary = state.get("summary", "")
    logger.info("Received summary: %d characters", len(summary))
    return {"summary": summary.strip(), "status": "processing"}
