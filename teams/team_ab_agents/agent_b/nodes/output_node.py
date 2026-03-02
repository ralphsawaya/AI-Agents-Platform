"""Output node — stores the title in MongoDB and finalises."""

from shared.logger import get_logger
from shared.mongo import get_collection

logger = get_logger("agent_b.output_node")


def output_node(state: dict) -> dict:
    if state.get("status") == "error":
        return state

    text_id = state.get("text_id", 0)
    doc = {
        "text_id": text_id,
        "agent_name": "AgentB",
        "title": state["title"],
    }

    col = get_collection()
    col.insert_one(doc)
    logger.info("Stored title in MongoDB with text_id=%d", text_id)

    return {"status": "complete"}
