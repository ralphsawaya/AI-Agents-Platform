"""Memory store for the Risk Manager — risk state history."""

from shared.mongo import get_risk_state


def get_current_risk_state() -> dict | None:
    """Retrieve the current risk state."""
    return get_risk_state().find_one(sort=[("updated_at", -1)])
