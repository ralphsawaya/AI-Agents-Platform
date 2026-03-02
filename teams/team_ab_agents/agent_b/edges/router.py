"""Edge router for AgentB."""


def should_continue(state: dict) -> str:
    if state.get("status") == "error":
        return "error_handler"
    return "continue"
