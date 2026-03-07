"""TypedDict state schema for the Risk Manager agent."""

from typing import TypedDict


class RiskManagerState(TypedDict):
    signal: dict
    account_balance: float
    btc_balance: float
    current_price: float
    current_exposure: float
    open_orders_count: int
    atr: float
    position_size: float
    stop_loss_price: float
    take_profit_price: float
    risk_amount: float
    approved: bool
    rejection_reason: str
    dry_run: bool
    status: str
