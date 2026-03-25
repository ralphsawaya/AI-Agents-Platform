"""Standalone entry point for the Voice Caller agent."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.utils import load_args
from shared.config import CALLS_PER_BATCH
from agent_voice_caller.agent import build_voice_caller_graph

logger = get_logger("agent_voice_caller")


def run():
    args = load_args()
    batch_size = int(args.get("batch_size", CALLS_PER_BATCH))

    logger.info("Voice Caller starting — batch_size=%d", batch_size)

    graph = build_voice_caller_graph()
    result = graph.invoke({
        "batch_size": batch_size,
        "leads_to_call": [],
        "call_results": [],
        "interested_count": 0,
        "not_interested_count": 0,
        "no_answer_count": 0,
        "status": "pending",
    })

    logger.info(
        "Voice Caller complete — interested=%d, not_interested=%d, no_answer=%d",
        result.get("interested_count", 0),
        result.get("not_interested_count", 0),
        result.get("no_answer_count", 0),
    )
    return result


if __name__ == "__main__":
    run()
