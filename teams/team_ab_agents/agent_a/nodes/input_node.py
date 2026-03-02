"""Input node — validates and prepares input text (max 500 words)."""

import time

from shared.logger import get_logger
from shared.utils import word_count

logger = get_logger("agent_a.input_node")

MAX_WORDS = 500


def input_node(state: dict) -> dict:
    text = state.get("input_text", "").strip()

    if not text:
        logger.error("No input text provided")
        return {"input_text": "", "status": "error"}

    wc = word_count(text)
    if wc > MAX_WORDS:
        logger.warning(
            "Input text has %d words, truncating to %d", wc, MAX_WORDS
        )
        text = " ".join(text.split()[:MAX_WORDS])
        wc = MAX_WORDS

    logger.info("Input accepted: %d words, %d characters", wc, len(text))
    logger.info("AgentA: pre-processing input (10s)…")
    time.sleep(10)
    return {"input_text": text, "word_count": wc, "status": "processing"}
