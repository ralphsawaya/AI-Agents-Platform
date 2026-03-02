"""Edge router for agent_beta."""


def should_continue(state: dict) -> str:
    if state.get("status") == "error":
        return "error_handler"
    return "continue"
