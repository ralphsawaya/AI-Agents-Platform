"""Edge routing logic for the Analyst agent."""


def check_data_status(state: dict) -> str:
    """Route based on whether data fetch succeeded."""
    if state.get("status") == "error":
        return "end"
    return "compute_indicators"
