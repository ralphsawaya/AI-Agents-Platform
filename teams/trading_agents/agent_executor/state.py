"""TypedDict state schema for the Executor agent."""

from typing import TypedDict


class ExecutorState(TypedDict):
    signal: dict
    risk_params: dict
    dry_run: bool
    order_id: str
    fill_price: float
    order_status: str
    stop_loss_order_id: str
    trade_record: dict
    status: str
