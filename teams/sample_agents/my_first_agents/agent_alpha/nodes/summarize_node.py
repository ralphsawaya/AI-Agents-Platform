"""Summarize node — uses LLM to create a concise summary."""

from shared.llm import get_llm
from shared.logger import get_logger
from shared.utils import word_count

logger = get_logger("agent_alpha.summarize_node")


def summarize_node(state: dict) -> dict:
    llm = get_llm()
    text = state["input_text"]

    prompt = f"Please summarize the following text concisely:\n\n{text}"
    logger.info("Calling LLM for summarization…")

    response = llm.invoke(prompt)
    summary = response if isinstance(response, str) else str(response.content)

    logger.info("Summary generated: %d words", word_count(summary))
    return {"summary": summary, "word_count": word_count(summary)}
