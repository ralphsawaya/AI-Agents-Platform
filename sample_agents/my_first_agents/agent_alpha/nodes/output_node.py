"""Output node — finalises the result."""

from shared.logger import get_logger

logger = get_logger("agent_alpha.output_node")


def output_node(state: dict) -> dict:
    logger.info("agent_alpha finished. Summary word count: %d", state.get("word_count", 0))
    return {"status": "complete"}
