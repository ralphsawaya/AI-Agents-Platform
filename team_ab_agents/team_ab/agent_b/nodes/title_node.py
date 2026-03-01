"""Title node — uses Gemini LLM to generate a title from the summary."""

from shared.llm import get_llm
from shared.logger import get_logger
from agent_b.prompts.prompt_templates import TITLE_TEMPLATE

logger = get_logger("agent_b.title_node")


def title_node(state: dict) -> dict:
    if state.get("status") == "error":
        return state

    llm = get_llm()
    summary = state["summary"]
    prompt = TITLE_TEMPLATE.format(summary=summary)

    logger.info("Calling Gemini LLM for title generation…")
    title = llm.invoke(prompt).strip().strip('"').strip("'")

    logger.info("Title generated: %s", title)
    return {"title": title}
