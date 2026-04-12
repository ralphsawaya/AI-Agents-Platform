"""Edge routing logic for the Flight Search agent."""


def check_embed_status(state: dict) -> str:
    if state.get("status") == "error":
        return "end"
    return "search_flights"
