"""Basic tests for the trading agent pipeline."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_analyst_state_schema():
    from agent_analyst.state import AnalystState
    state: AnalystState = {
        "ohlcv_4h": [],
        "ohlcv_1h": [],
        "indicators": {},
        "regime": "ranging",
        "confidence": 0.8,
        "reasoning": "test",
        "status": "pending",
    }
    assert state["regime"] == "ranging"


def test_strategist_state_schema():
    from agent_strategist.state import StrategistState
    state: StrategistState = {
        "regime": "trending_up",
        "confidence": 0.9,
        "indicators": {},
        "strategy_candidates": ["trend_following"],
        "selected_strategy": "trend_following",
        "reasoning": "test",
        "status": "pending",
    }
    assert state["selected_strategy"] == "trend_following"


def test_risk_manager_state_schema():
    from agent_risk_manager.state import RiskManagerState
    state: RiskManagerState = {
        "signal": {"action": "buy"},
        "account_balance": 1000.0,
        "btc_balance": 0.0,
        "current_price": 50000.0,
        "current_exposure": 0.0,
        "open_orders_count": 0,
        "atr": 500.0,
        "position_size": 0.001,
        "stop_loss_price": 49000.0,
        "take_profit_price": 52000.0,
        "risk_amount": 20.0,
        "approved": True,
        "rejection_reason": "",
        "dry_run": True,
        "status": "pending",
    }
    assert state["approved"] is True


def test_executor_state_schema():
    from agent_executor.state import ExecutorState
    state: ExecutorState = {
        "signal": {"action": "buy", "ticker": "BTCUSDT"},
        "risk_params": {"position_size": 0.001, "approved": True},
        "dry_run": True,
        "order_id": "",
        "fill_price": 0.0,
        "order_status": "",
        "stop_loss_order_id": "",
        "trade_record": {},
        "status": "pending",
    }
    assert state["dry_run"] is True


def test_regime_strategy_mapping():
    from agent_strategist.nodes.evaluate_strategies import REGIME_STRATEGY_MAP
    assert "trend_following" in REGIME_STRATEGY_MAP["trending_up"]
    assert "trend_following" in REGIME_STRATEGY_MAP["trending_down"]
    assert "mean_reversion" in REGIME_STRATEGY_MAP["ranging"]
    assert "scalping" in REGIME_STRATEGY_MAP["high_volatility"]


def test_indicators_model():
    from shared.models import Indicators
    ind = Indicators(adx=25.0, rsi=50.0, current_price=50000.0)
    assert ind.adx == 25.0
    assert ind.rsi == 50.0
