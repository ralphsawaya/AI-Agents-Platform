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
        "regime": "uptrend",
        "confidence": 0.9,
        "indicators": {},
        "strategy_candidates": ["ema_trend"],
        "selected_strategy": "ema_trend",
        "reasoning": "test",
        "status": "pending",
    }
    assert state["selected_strategy"] == "ema_trend"


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
    assert "ema_trend" in REGIME_STRATEGY_MAP["uptrend"]
    assert "rsi_momentum" in REGIME_STRATEGY_MAP["uptrend"]
    assert "macd_trend" in REGIME_STRATEGY_MAP["uptrend"]
    assert "ema_trend" in REGIME_STRATEGY_MAP["downtrend"]
    assert "rsi_momentum" in REGIME_STRATEGY_MAP["ranging"]
    assert "rsi_momentum" in REGIME_STRATEGY_MAP["volatile_breakout"]
    assert "macd_trend" in REGIME_STRATEGY_MAP["volatile_breakout"]
    # Legacy regime names still map correctly
    assert "ema_trend" in REGIME_STRATEGY_MAP["trending_up"]
    assert "rsi_momentum" in REGIME_STRATEGY_MAP["accumulation"]


def test_regime_types():
    from shared.models import MarketRegimeType, ACTIVE_REGIMES
    assert MarketRegimeType.UPTREND.value == "uptrend"
    assert MarketRegimeType.DOWNTREND.value == "downtrend"
    assert MarketRegimeType.RANGING.value == "ranging"
    assert MarketRegimeType.VOLATILE_BREAKOUT.value == "volatile_breakout"
    assert len(ACTIVE_REGIMES) == 4


def test_strategy_names():
    from shared.models import StrategyName
    assert StrategyName.EMA_TREND.value == "ema_trend"
    assert StrategyName.RSI_MOMENTUM.value == "rsi_momentum"
    assert StrategyName.MACD_TREND.value == "macd_trend"
    # Legacy names still exist for backward compatibility
    assert StrategyName.TREND_FOLLOWING.value == "trend_following"
    assert StrategyName.MEAN_REVERSION.value == "mean_reversion"


def test_indicators_model():
    from shared.models import Indicators
    ind = Indicators(adx=25.0, rsi=50.0, current_price=50000.0)
    assert ind.adx == 25.0
    assert ind.rsi == 50.0


def test_quantitative_regime_classifier():
    from agent_analyst.nodes.classify_regime import _quantitative_regime
    # Uptrend: ADX > 22, EMA alignment, positive slope
    assert _quantitative_regime({
        "adx": 30, "ema_fast": 100, "ema_mid": 95, "ema_slow": 90,
        "ema_slow_slope": 0.5, "atr_pct": 1.0, "bb_width": 2.0, "bb_middle": 100,
        "volume_ratio": 1.0,
    }) == "uptrend"
    # Downtrend: reverse alignment
    assert _quantitative_regime({
        "adx": 30, "ema_fast": 90, "ema_mid": 95, "ema_slow": 100,
        "ema_slow_slope": -0.5, "atr_pct": 1.0, "bb_width": 2.0, "bb_middle": 100,
        "volume_ratio": 1.0,
    }) == "downtrend"
    # Ranging: low ADX
    assert _quantitative_regime({
        "adx": 15, "ema_fast": 100, "ema_mid": 99, "ema_slow": 98,
        "ema_slow_slope": 0.1, "atr_pct": 1.0, "bb_width": 2.0, "bb_middle": 100,
        "volume_ratio": 1.0,
    }) == "ranging"
    # Volatile breakout: high ATR + wide BB + volume
    assert _quantitative_regime({
        "adx": 30, "ema_fast": 100, "ema_mid": 95, "ema_slow": 90,
        "ema_slow_slope": 0.5, "atr_pct": 3.0, "bb_width": 5.0, "bb_middle": 100,
        "volume_ratio": 2.0,
    }) == "volatile_breakout"


def test_risk_manager_strategy_config():
    from agent_risk_manager.nodes.calculate_risk import STRATEGY_ATR_MULT, STRATEGY_TP_RATIO
    from agent_risk_manager.nodes.fetch_account import STRATEGY_TIMEFRAME
    for strat in ["ema_trend", "rsi_momentum", "macd_trend"]:
        assert strat in STRATEGY_ATR_MULT, f"{strat} missing from ATR mult"
        assert strat in STRATEGY_TP_RATIO, f"{strat} missing from TP ratio"
        assert strat in STRATEGY_TIMEFRAME, f"{strat} missing from timeframe map"
