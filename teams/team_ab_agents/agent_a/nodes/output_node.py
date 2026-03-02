"""Output node — stores the summary in MongoDB and finalises."""

import time

from shared.logger import get_logger
from shared.mongo import get_collection, get_next_text_id

logger = get_logger("agent_a.output_node")


def output_node(state: dict) -> dict:
    if state.get("status") == "error":
        return state

    text_id = get_next_text_id()
    doc = {
        "text_id": text_id,
        "agent_name": "AgentA",
        "initial_text": state["input_text"],
        "summary_text": state["summary"],
    }

    col = get_collection()
    col.insert_one(doc)
    logger.info("Stored summary in MongoDB with text_id=%d — finalising AgentA (5s)…", text_id)
    time.sleep(5)
    return {"text_id": text_id, "status": "complete"}
