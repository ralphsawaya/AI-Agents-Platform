"""Supervisor logic for the trading orchestrator (reserved for future use)."""


def should_continue(state: dict) -> bool:
    """Determine whether the pipeline should continue or halt."""
    return state.get("status") != "error"
