"""Entry point for AgentB (Title Writer)."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.utils import load_args
from agent_b.agent import build_agent_b_graph

logger = get_logger("agent_b")


def run(summary: str = "", text_id: int = 0):
    args = load_args()
    summary = summary or args.get("summary", "No summary provided.")
    text_id = text_id or args.get("text_id", 0)

    logger.info("AgentB starting with summary of %d chars", len(summary))

    graph = build_agent_b_graph()
    result = graph.invoke({
        "summary": summary,
        "title": "",
        "text_id": text_id,
        "status": "pending",
    })

    logger.info("AgentB complete — title: %s", result.get("title", ""))
    return result


if __name__ == "__main__":
    run()
