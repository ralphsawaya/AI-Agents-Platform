"""Output node — finalises the report result."""

from shared.logger import get_logger

logger = get_logger("agent_beta.output_node")


def output_node(state: dict) -> dict:
    logger.info("agent_beta finished. Report title: %s", state.get("title", ""))
    return {"status": "complete"}
