"""Summarize node — uses Gemini LLM to create a concise summary."""

from shared.llm import get_llm
from shared.logger import get_logger
from shared.utils import word_count
from agent_a.prompts.prompt_templates import SUMMARIZE_TEMPLATE

logger = get_logger("agent_a.summarize_node")


def summarize_node(state: dict) -> dict:
    if state.get("status") == "error":
        return state

    llm = get_llm()
    text = state["input_text"]
    prompt = SUMMARIZE_TEMPLATE.format(text=text)

    logger.info("Calling Gemini LLM for summarization…")
    summary = llm.invoke(prompt)

    logger.info("Summary generated: %d words", word_count(summary))
    return {"summary": summary, "word_count": word_count(summary)}
