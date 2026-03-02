"""Report node — generates a structured markdown report from the summary."""

from shared.llm import get_llm
from shared.logger import get_logger

logger = get_logger("agent_beta.report_node")


def report_node(state: dict) -> dict:
    llm = get_llm()
    summary = state["summary"]

    prompt = (
        f"Based on the following summary, generate a professional "
        f"structured report in markdown format with sections for "
        f"Executive Summary, Key Findings, and Recommendations:\n\n"
        f"{summary}"
    )
    logger.info("Calling LLM for report generation…")

    response = llm.invoke(prompt)
    report = response if isinstance(response, str) else str(response.content)

    title = "Analysis Report"
    logger.info("Report generated: %d characters", len(report))
    return {"report": report, "title": title}
