"""Orchestrator entry point.

This is the file executed by the platform when running the agent package.
It builds the master graph (AgentA -> AgentB) and runs it.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.utils import load_args
from orchestrator.graph import build_orchestrator_graph

logger = get_logger("orchestrator")


def main():
    args = load_args()
    input_text = args.get("text", "")

    if not input_text:
        print("=" * 60)
        print("TeamAB Pipeline — Paste a text paragraph (max 500 words).")
        print("Press Enter twice when done:")
        print("=" * 60)
        lines = []
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
        input_text = "\n".join(lines)

    if not input_text.strip():
        input_text = (
            "Artificial intelligence has transformed many industries. "
            "Machine learning models can now process natural language, "
            "generate images, and assist with complex decision-making tasks. "
            "The field continues to evolve rapidly with new architectures "
            "and training techniques being developed regularly. "
            "Organizations are increasingly adopting AI solutions to "
            "improve efficiency, reduce costs, and gain competitive advantages. "
            "However, challenges remain in areas such as bias, interpretability, "
            "and responsible deployment of these powerful technologies."
        )

    logger.info("=" * 60)
    logger.info("Orchestrator starting TeamAB pipeline")
    logger.info("Input: %d characters", len(input_text))
    logger.info("=" * 60)

    graph = build_orchestrator_graph()
    result = graph.invoke({
        "input_text": input_text,
        "summary": "",
        "title": "",
        "text_id": 0,
        "current_agent": "",
        "status": "pending",
    })

    logger.info("=" * 60)
    logger.info("Pipeline complete!")
    logger.info("Summary: %s", result.get("summary", "")[:200])
    logger.info("Title: %s", result.get("title", ""))
    logger.info("Text ID: %d", result.get("text_id", 0))
    logger.info("Final status: %s", result.get("status"))
    logger.info("=" * 60)

    print("\n--- RESULTS ---")
    print(f"Title:   {result.get('title', 'N/A')}")
    print(f"Summary: {result.get('summary', 'N/A')}")
    print(f"Text ID: {result.get('text_id', 'N/A')}")

    return result


if __name__ == "__main__":
    main()
