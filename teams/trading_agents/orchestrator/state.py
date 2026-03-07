"""Shared orchestrator state that flows between trading agents."""

from typing import TypedDict


class AnalysisPipelineState(TypedDict):
    # Analyst state
    ohlcv_4h: list
    ohlcv_1h: list
    indicators: dict
    regime: str
    confidence: float
    reasoning: str
    # Strategist state
    strategy_candidates: list
    selected_strategy: str
    # Shared
    current_agent: str
    status: str


class ExecutionPipelineState(TypedDict):
    # Signal from webhook
    signal: dict
    dry_run: bool
    # Risk Manager state
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
    # Executor state
    risk_params: dict
    order_id: str
    fill_price: float
    order_status: str
    stop_loss_order_id: str
    trade_record: dict
    # Shared
    current_agent: str
    status: str
