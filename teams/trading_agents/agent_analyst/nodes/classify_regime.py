"""Classify the current market regime using Gemini and indicator data."""

from datetime import datetime, timezone

from shared.llm import get_llm
from shared.logger import get_logger
from shared.mongo import get_market_regimes
from agent_analyst.prompts.prompt_templates import REGIME_CLASSIFICATION_PROMPT

logger = get_logger("analyst.classify_regime")

VALID_REGIMES = {"trending_up", "trending_down", "ranging", "high_volatility", "breakout", "accumulation"}


def classify_regime(state: dict) -> dict:
    if state.get("status") == "error":
        return state

    indicators = state.get("indicators", {})
    if not indicators:
        return {"status": "error", "reasoning": "No indicators available"}

    llm = get_llm()
    prompt = REGIME_CLASSIFICATION_PROMPT.format(
        price=indicators.get("current_price", 0),
        adx=indicators.get("adx", 0),
        atr=indicators.get("atr", 0),
        atr_pct=indicators.get("atr_pct", 0),
        bb_width=indicators.get("bb_width", 0),
        bb_upper=indicators.get("bb_upper", 0),
        bb_lower=indicators.get("bb_lower", 0),
        bb_middle=indicators.get("bb_middle", 0),
        ema_fast=indicators.get("ema_fast", 0),
        ema_mid=indicators.get("ema_mid", 0),
        ema_slow=indicators.get("ema_slow", 0),
        ema_fast_slope=indicators.get("ema_fast_slope", 0),
        ema_mid_slope=indicators.get("ema_mid_slope", 0),
        ema_slow_slope=indicators.get("ema_slow_slope", 0),
        rsi=indicators.get("rsi", 0),
        macd=indicators.get("macd", 0),
        macd_signal=indicators.get("macd_signal", 0),
        macd_hist=indicators.get("macd_hist", 0),
        volume_ratio=indicators.get("volume_ratio", 0),
    )

    logger.info("Calling Gemini for regime classification…")
    response = llm.invoke(prompt)

    regime, confidence, reasoning = _parse_response(response)
    logger.info("Regime: %s (confidence: %.0f%%)", regime, confidence * 100)
    logger.info("Reasoning: %s", reasoning[:200])

    regime_doc = {
        "regime": regime,
        "confidence": confidence,
        "reasoning": reasoning,
        "indicators": indicators,
        "timestamp": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
    }
    get_market_regimes().insert_one(regime_doc)

    return {
        "regime": regime,
        "confidence": confidence,
        "reasoning": reasoning,
        "status": "regime_classified",
    }


def _parse_response(response: str) -> tuple[str, float, str]:
    """Extract regime, confidence, and reasoning from Gemini's response."""
    lines = response.strip().split("\n")
    regime = "ranging"
    confidence = 0.5
    reasoning_parts = []

    for line in lines:
        lower = line.lower().strip()
        if lower.startswith("regime:"):
            val = lower.split(":", 1)[1].strip()
            if val in VALID_REGIMES:
                regime = val
        elif lower.startswith("confidence:"):
            try:
                val = lower.split(":", 1)[1].strip().rstrip("%")
                confidence = float(val) / 100 if float(val) > 1 else float(val)
            except ValueError:
                pass
        elif lower.startswith("reasoning:"):
            reasoning_parts.append(line.split(":", 1)[1].strip())
        else:
            if reasoning_parts:
                reasoning_parts.append(line.strip())

    return regime, min(max(confidence, 0.0), 1.0), " ".join(reasoning_parts) or response[:500]
