"""Entry point for agent_alpha (Summarizer)."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.utils import load_args
from agent_alpha.agent import build_alpha_graph

logger = get_logger("agent_alpha")


def run():
    args = load_args()
    input_text = args.get("text", "The quick brown fox jumps over the lazy dog. " * 20)

    logger.info("agent_alpha starting with %d chars of input", len(input_text))

    graph = build_alpha_graph()
    result = graph.invoke({
        "input_text": input_text,
        "summary": "",
        "word_count": 0,
        "status": "pending",
    })

    logger.info("agent_alpha complete — summary: %s", result.get("summary", "")[:100])
    return result


if __name__ == "__main__":
    run()
