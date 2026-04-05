"""Evaluate which strategies are compatible with the current regime.

Regime-strategy mapping supports parallel execution — multiple strategies
can be active simultaneously when their target regimes match.
"""

from shared.logger import get_logger

logger = get_logger("strategist.evaluate_strategies")

REGIME_STRATEGY_MAP = {
    "uptrend": ["ema_trend", "rsi_momentum", "macd_trend"],
    "downtrend": ["ema_trend", "rsi_momentum", "macd_trend"],
    "ranging": ["rsi_momentum"],
    "volatile_breakout": ["rsi_momentum", "macd_trend"],
    # Legacy regime names
    "trending_up": ["ema_trend", "rsi_momentum", "macd_trend"],
    "trending_down": ["ema_trend", "rsi_momentum", "macd_trend"],
    "high_volatility": ["rsi_momentum", "macd_trend"],
    "breakout": ["rsi_momentum", "macd_trend"],
    "accumulation": ["rsi_momentum"],
}

ALL_STRATEGIES = ["ema_trend", "rsi_momentum", "macd_trend"]


def evaluate_strategies(state: dict) -> dict:
    regime = state.get("regime", "ranging")
    confidence = state.get("confidence", 0.0)

    candidates = REGIME_STRATEGY_MAP.get(regime, ["rsi_momentum"])

    if confidence < 0.5:
        candidates = ALL_STRATEGIES
        logger.info(
            "Low confidence (%.0f%%) — all strategies are candidates",
            confidence * 100,
        )
    else:
        logger.info(
            "Regime '%s' (%.0f%% confidence) — candidates: %s",
            regime, confidence * 100, candidates,
        )

    return {"strategy_candidates": candidates, "status": "candidates_evaluated"}
