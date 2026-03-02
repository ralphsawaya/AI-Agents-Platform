"""Edge router for agent_alpha (not used in this simple graph)."""


def should_continue(state: dict) -> str:
    if state.get("status") == "error":
        return "error_handler"
    return "continue"
