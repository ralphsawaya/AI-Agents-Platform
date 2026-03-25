"""Edge routing logic for the Voice Caller agent."""


def should_continue(state: dict) -> str:
    if state.get("status") in ("error", "no_leads"):
        return "end"
    return "continue"
