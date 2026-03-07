"""Edge routing logic for the Strategist agent."""


def route_strategy(state: dict) -> str:
    """Route based on number of candidates."""
    candidates = state.get("strategy_candidates", [])
    if len(candidates) == 1 and state.get("confidence", 0) >= 0.7:
        return "update_selection"
    return "select_strategy"
