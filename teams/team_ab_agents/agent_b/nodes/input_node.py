"""Input node — receives summary text from AgentA."""

import time

from shared.logger import get_logger

logger = get_logger("agent_b.input_node")


def input_node(state: dict) -> dict:
    summary = state.get("summary", "").strip()

    if not summary:
        logger.error("No summary text received from AgentA")
        return {"summary": "", "status": "error"}

    logger.info("Received summary: %d characters — AgentB initialising (5s)…", len(summary))
    time.sleep(5)
    return {"summary": summary, "status": "processing"}
