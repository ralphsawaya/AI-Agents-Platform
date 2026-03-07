"""Orchestrator entry point for the trading agent team.

Supports two modes via AGENT_ARGS:
  - mode=analysis: Runs the analysis pipeline (Analyst -> Strategist)
  - mode=execution: Runs the execution pipeline (Risk Manager -> Executor)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.utils import load_args
from orchestrator.graph import build_analysis_graph, build_execution_graph

logger = get_logger("orchestrator")


def main():
    args = load_args()
    mode = args.get("mode", "analysis")

    logger.info("=" * 60)
    logger.info("Trading Orchestrator — mode: %s", mode)
    logger.info("=" * 60)

    if mode == "analysis":
        return run_analysis()
    elif mode == "execution":
        return run_execution(args)
    else:
        logger.error("Unknown mode: %s (expected 'analysis' or 'execution')", mode)
        return None


def run_analysis():
    """Run the analysis pipeline: Analyst -> Strategist."""
    logger.info("Starting analysis pipeline…")

    graph = build_analysis_graph()
    result = graph.invoke({
        "ohlcv_4h": [],
        "ohlcv_1h": [],
        "indicators": {},
        "regime": "",
        "confidence": 0.0,
        "reasoning": "",
        "strategy_candidates": [],
        "selected_strategy": "",
        "current_agent": "",
        "status": "pending",
    })

    logger.info("=" * 60)
    logger.info("Analysis pipeline complete!")
    logger.info("Regime: %s (confidence: %.0f%%)", result.get("regime", ""), result.get("confidence", 0) * 100)
    logger.info("Selected strategy: %s", result.get("selected_strategy", ""))
    logger.info("Reasoning: %s", result.get("reasoning", "")[:300])
    logger.info("=" * 60)

    print("\n--- ANALYSIS RESULTS ---")
    print(f"Regime:   {result.get('regime', 'N/A')}")
    print(f"Confidence: {result.get('confidence', 0):.0%}")
    print(f"Strategy: {result.get('selected_strategy', 'N/A')}")

    return result


def run_execution(args: dict):
    """Run the execution pipeline: Risk Manager -> Executor."""
    signal = args.get("signal", {})
    dry_run = args.get("dry_run", True)

    if not signal:
        logger.error("No signal provided for execution mode")
        return None

    logger.info(
        "Starting execution pipeline — %s %s @ %.2f (dry_run=%s)",
        signal.get("action", ""),
        signal.get("ticker", ""),
        signal.get("price", 0),
        dry_run,
    )

    graph = build_execution_graph()
    result = graph.invoke({
        "signal": signal,
        "dry_run": dry_run,
        "account_balance": 0.0,
        "btc_balance": 0.0,
        "current_price": 0.0,
        "current_exposure": 0.0,
        "open_orders_count": 0,
        "atr": 0.0,
        "position_size": 0.0,
        "stop_loss_price": 0.0,
        "take_profit_price": 0.0,
        "risk_amount": 0.0,
        "approved": False,
        "rejection_reason": "",
        "risk_params": {},
        "order_id": "",
        "fill_price": 0.0,
        "order_status": "",
        "stop_loss_order_id": "",
        "trade_record": {},
        "current_agent": "",
        "status": "pending",
    })

    logger.info("=" * 60)
    logger.info("Execution pipeline complete!")
    logger.info("Approved: %s", result.get("approved", False))
    logger.info("Order ID: %s", result.get("order_id", "N/A"))
    logger.info("Fill Price: %.2f", result.get("fill_price", 0))
    logger.info("Order Status: %s", result.get("order_status", ""))
    logger.info("=" * 60)

    print("\n--- EXECUTION RESULTS ---")
    print(f"Approved:    {result.get('approved', False)}")
    print(f"Order ID:    {result.get('order_id', 'N/A')}")
    print(f"Fill Price:  {result.get('fill_price', 0):.2f}")
    print(f"Status:      {result.get('order_status', 'N/A')}")

    return result


if __name__ == "__main__":
    main()
