"""Conditional routing for the orchestrator."""


def route_by_mode(state: dict) -> str:
    mode = state.get("mode", "search")
    if mode == "reserve":
        return "create_reservation"
    return "parse_query"
