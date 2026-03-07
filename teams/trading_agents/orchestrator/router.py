"""Conditional routing for the orchestrator."""


def route_by_mode(state: dict) -> str:
    """Determine pipeline mode from state."""
    mode = state.get("mode", "analysis")
    if mode == "execution":
        return "risk_manager"
    return "analyst"
