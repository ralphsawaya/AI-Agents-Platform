"""Report formatting tools for agent_beta."""

from langchain_core.tools import tool


@tool
def format_markdown_report(title: str, sections: list[str]) -> str:
    """Format a list of sections into a markdown report."""
    report = f"# {title}\n\n"
    for section in sections:
        report += f"{section}\n\n"
    return report
