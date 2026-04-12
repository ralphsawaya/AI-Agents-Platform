"""Supervisor logic for the trip orchestrator (reserved for future use)."""


def should_continue(state: dict) -> bool:
    return state.get("status") != "error"
