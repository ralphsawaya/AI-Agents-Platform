"""Input node — validates and prepares input text."""

from shared.logger import get_logger

logger = get_logger("agent_alpha.input_node")


def input_node(state: dict) -> dict:
    text = state.get("input_text", "")
    logger.info("Input received: %d characters", len(text))
    return {"input_text": text.strip(), "status": "processing"}
