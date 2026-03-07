"""Evaluate which strategies are compatible with the current regime."""

from shared.logger import get_logger

logger = get_logger("strategist.evaluate_strategies")

REGIME_STRATEGY_MAP = {
    "trending_up": ["trend_following"],
    "trending_down": ["trend_following"],
    "ranging": ["mean_reversion"],
    "high_volatility": ["scalping"],
    "breakout": ["trend_following"],
    "accumulation": ["mean_reversion"],
}

ALL_STRATEGIES = ["trend_following", "mean_reversion", "scalping"]


def evaluate_strategies(state: dict) -> dict:
    regime = state.get("regime", "ranging")
    confidence = state.get("confidence", 0.0)

    candidates = REGIME_STRATEGY_MAP.get(regime, ["mean_reversion"])

    # Low-confidence regimes get all strategies as candidates for LLM evaluation
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
