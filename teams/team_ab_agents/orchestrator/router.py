"""Orchestrator routing logic."""


def route_next_agent(state: dict) -> str:
    """Determine which agent to run next based on current state."""
    status = state.get("status", "")
    if status == "agent_a_complete":
        return "agent_b"
    return "end"
