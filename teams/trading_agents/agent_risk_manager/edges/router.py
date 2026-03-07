"""Edge routing logic for the Risk Manager agent."""


def check_approval(state: dict) -> str:
    """Route based on trade approval status."""
    if state.get("approved"):
        return "approved"
    return "rejected"
