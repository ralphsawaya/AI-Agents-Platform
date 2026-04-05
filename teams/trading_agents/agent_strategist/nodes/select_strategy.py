"""Select the best strategy from candidates using LLM for edge cases."""

from shared.llm import get_llm
from shared.logger import get_logger
from agent_strategist.prompts.prompt_templates import STRATEGY_SELECTION_PROMPT

logger = get_logger("strategist.select_strategy")

VALID_STRATEGIES = {"ema_trend", "rsi_momentum", "macd_trend"}


def select_strategy(state: dict) -> dict:
    candidates = state.get("strategy_candidates", [])
    regime = state.get("regime", "ranging")
    confidence = state.get("confidence", 0.0)
    indicators = state.get("indicators", {})

    if len(candidates) == 1 and confidence >= 0.7:
        selected = candidates[0]
        reasoning = f"Clear {regime} regime with {confidence:.0%} confidence — {selected} is the optimal strategy."
        logger.info("Fast path: %s", selected)
        return {
            "selected_strategy": selected,
            "reasoning": reasoning,
            "status": "strategy_selected",
        }

    llm = get_llm()
    prompt = STRATEGY_SELECTION_PROMPT.format(
        regime=regime,
        confidence=confidence * 100,
        candidates=", ".join(candidates),
        adx=indicators.get("adx", 0),
        atr_pct=indicators.get("atr_pct", 0),
        rsi=indicators.get("rsi", 0),
        bb_width=indicators.get("bb_width", 0),
        volume_ratio=indicators.get("volume_ratio", 0),
    )

    logger.info("Consulting LLM for strategy selection...")
    response = llm.invoke(prompt)

    selected, reasoning = _parse_response(response, candidates)
    logger.info("Selected strategy: %s", selected)

    return {
        "selected_strategy": selected,
        "reasoning": reasoning,
        "status": "strategy_selected",
    }


def _parse_response(response: str, candidates: list[str]) -> tuple[str, str]:
    lines = response.strip().split("\n")
    selected = candidates[0] if candidates else "rsi_momentum"
    reasoning = response[:500]

    for line in lines:
        lower = line.lower().strip()
        if lower.startswith("strategy:"):
            val = lower.split(":", 1)[1].strip()
            if val in VALID_STRATEGIES:
                selected = val
        elif lower.startswith("reasoning:"):
            reasoning = line.split(":", 1)[1].strip()

    return selected, reasoning
