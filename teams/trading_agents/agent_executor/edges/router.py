"""Edge routing logic for the Executor agent."""


def check_order_status(state: dict) -> str:
    """Route based on order placement result."""
    if state.get("status") in ("error", "rejected"):
        return "end"
    return "confirm_order"
