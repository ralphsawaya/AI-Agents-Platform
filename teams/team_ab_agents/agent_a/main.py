"""Entry point for AgentA (Summarizer)."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.utils import load_args
from agent_a.agent import build_agent_a_graph

logger = get_logger("agent_a")


def run():
    args = load_args()
    input_text = args.get("text", "")

    if not input_text:
        input_text = input("Paste your text paragraph (max 500 words):\n> ")

    logger.info("AgentA starting with %d chars of input", len(input_text))

    graph = build_agent_a_graph()
    result = graph.invoke({
        "input_text": input_text,
        "summary": "",
        "text_id": 0,
        "word_count": 0,
        "status": "pending",
    })

    logger.info("AgentA complete — summary: %s", result.get("summary", "")[:100])
    return result


if __name__ == "__main__":
    run()
