"""Classify the current market regime using LLM + quantitative cross-check.

Uses a simplified 4-regime model (UPTREND, DOWNTREND, RANGING,
VOLATILE_BREAKOUT) with multi-indicator quantitative baseline and
LLM confirmation.
"""

from datetime import datetime, timezone

from shared.llm import get_llm
from shared.logger import get_logger
from shared.mongo import get_market_regimes
from agent_analyst.prompts.prompt_templates import REGIME_CLASSIFICATION_PROMPT

logger = get_logger("analyst.classify_regime")

VALID_REGIMES = {"uptrend", "downtrend", "ranging", "volatile_breakout"}

CROSSCHECK_CONFIDENCE_THRESHOLD = 0.65


def _quantitative_regime(ind: dict) -> str:
    """Pure indicator-based regime classification (deterministic fallback).

    Priority order:
      1. Volatile breakout  (ATR% > 2.5 + wide BB + volume surge)
      2. Uptrend            (ADX > 22 + EMA triple alignment + positive slope)
      3. Downtrend          (ADX > 22 + EMA reverse alignment + negative slope)
      4. Ranging            (default)
    """
    adx = ind.get("adx", 0)
    atr_pct = ind.get("atr_pct", 0)
    bb_width = ind.get("bb_width", 0)
    bb_middle = ind.get("bb_middle", 0)
    ema_fast = ind.get("ema_fast", 0)
    ema_mid = ind.get("ema_mid", 0)
    ema_slow = ind.get("ema_slow", 0)
    ema_slow_slope = ind.get("ema_slow_slope", 0)
    volume_ratio = ind.get("volume_ratio", 0)

    bb_width_pct = (bb_width / bb_middle * 100) if bb_middle else 0

    if atr_pct > 2.5 and bb_width_pct > 4.0 and volume_ratio > 1.5:
        return "volatile_breakout"

    if adx > 22 and ema_fast > ema_mid > ema_slow and ema_slow_slope > 0:
        return "uptrend"

    if adx > 22 and ema_fast < ema_mid < ema_slow and ema_slow_slope < 0:
        return "downtrend"

    return "ranging"


def classify_regime(state: dict) -> dict:
    if state.get("status") == "error":
        return state

    indicators = state.get("indicators", {})
    if not indicators:
        return {"status": "error", "reasoning": "No indicators available"}

    quant_regime = _quantitative_regime(indicators)
    logger.info("Quantitative regime: %s", quant_regime)

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

    logger.info("Calling LLM for regime classification...")
    response = llm.invoke(prompt)

    llm_regime, llm_confidence, reasoning = _parse_response(response)
    logger.info("LLM regime: %s (confidence: %.0f%%)", llm_regime, llm_confidence * 100)

    regime = llm_regime
    confidence = llm_confidence
    if llm_regime != quant_regime:
        if llm_confidence < CROSSCHECK_CONFIDENCE_THRESHOLD:
            logger.warning(
                "LLM (%s @ %.0f%%) disagrees with quant (%s) — low confidence, using quant",
                llm_regime, llm_confidence * 100, quant_regime,
            )
            regime = quant_regime
            confidence = max(llm_confidence, 0.5)
            reasoning = (
                f"Quantitative override: LLM suggested {llm_regime} ({llm_confidence:.0%}) "
                f"but indicators point to {quant_regime}. {reasoning}"
            )
        else:
            logger.info(
                "LLM (%s @ %.0f%%) differs from quant (%s) — confidence sufficient, keeping LLM",
                llm_regime, llm_confidence * 100, quant_regime,
            )

    logger.info("Final regime: %s (confidence: %.0f%%)", regime, confidence * 100)

    regime_doc = {
        "regime": regime,
        "confidence": confidence,
        "reasoning": reasoning,
        "quant_regime": quant_regime,
        "llm_regime": llm_regime,
        "llm_confidence": llm_confidence,
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
    """Extract regime, confidence, and reasoning from LLM response."""
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
