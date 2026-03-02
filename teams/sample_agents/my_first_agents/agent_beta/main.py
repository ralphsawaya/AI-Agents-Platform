"""Entry point for agent_beta (Report Generator)."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.utils import load_args
from agent_beta.agent import build_beta_graph

logger = get_logger("agent_beta")


def run(summary: str = ""):
    args = load_args()
    summary = summary or args.get("summary", "No summary provided.")

    logger.info("agent_beta starting with summary of %d chars", len(summary))

    graph = build_beta_graph()
    result = graph.invoke({
        "summary": summary,
        "report": "",
        "title": "",
        "status": "pending",
    })

    logger.info("agent_beta complete — report length: %d chars", len(result.get("report", "")))
    return result


if __name__ == "__main__":
    run()
