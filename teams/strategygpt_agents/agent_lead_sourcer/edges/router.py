"""Edge routing logic for the Lead Sourcer agent."""


def should_continue(state: dict) -> str:
    if state.get("status") == "error":
        return "end"
    return "continue"
