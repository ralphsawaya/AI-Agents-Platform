"""Conditional routing for the orchestrator."""


def route_by_mode(state: dict) -> str:
    """Determine pipeline mode from state."""
    mode = state.get("mode", "full")
    if mode == "outreach":
        return "voice_caller"
    return "lead_sourcer"
