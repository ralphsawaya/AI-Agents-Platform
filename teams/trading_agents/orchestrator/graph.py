"""Dual-mode orchestrator: Analysis pipeline and Execution pipeline.

Analysis Pipeline (scheduled every 5 min):
    analyst -> strategist -> END

Execution Pipeline (webhook-triggered):
    risk_manager -> executor -> END
"""

from langgraph.graph import StateGraph, END

from orchestrator.state import AnalysisPipelineState, ExecutionPipelineState
from agent_analyst.agent import build_analyst_graph
from agent_strategist.agent import build_strategist_graph
from agent_risk_manager.agent import build_risk_manager_graph
from agent_executor.agent import build_executor_graph
from shared.logger import get_logger

logger = get_logger("orchestrator.graph")


# ── Analysis Pipeline Nodes ──────────────────────────────────────────

def run_analyst(state: dict) -> dict:
    """Execute the Analyst agent's market regime classification."""
    logger.info("Orchestrator: running Analyst")
    analyst_graph = build_analyst_graph()
    result = analyst_graph.invoke({
        "ohlcv_4h": [],
        "ohlcv_1h": [],
        "indicators": {},
        "regime": "",
        "confidence": 0.0,
        "reasoning": "",
        "status": "pending",
    })
    return {
        "ohlcv_4h": result.get("ohlcv_4h", []),
        "ohlcv_1h": result.get("ohlcv_1h", []),
        "indicators": result.get("indicators", {}),
        "regime": result.get("regime", ""),
        "confidence": result.get("confidence", 0.0),
        "reasoning": result.get("reasoning", ""),
        "current_agent": "analyst",
        "status": result.get("status", ""),
    }


def run_strategist(state: dict) -> dict:
    """Execute the Strategist agent's strategy selection."""
    logger.info("Orchestrator: running Strategist")
    strategist_graph = build_strategist_graph()
    result = strategist_graph.invoke({
        "regime": state["regime"],
        "confidence": state["confidence"],
        "indicators": state.get("indicators", {}),
        "strategy_candidates": [],
        "selected_strategy": "",
        "reasoning": "",
        "status": "pending",
    })
    return {
        "strategy_candidates": result.get("strategy_candidates", []),
        "selected_strategy": result.get("selected_strategy", ""),
        "reasoning": result.get("reasoning", ""),
        "current_agent": "strategist",
        "status": "complete",
    }


# ── Execution Pipeline Nodes ─────────────────────────────────────────

def run_risk_manager(state: dict) -> dict:
    """Execute the Risk Manager agent's position sizing and approval."""
    logger.info("Orchestrator: running Risk Manager")
    risk_graph = build_risk_manager_graph()
    result = risk_graph.invoke({
        "signal": state["signal"],
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
        "dry_run": state.get("dry_run", True),
        "status": "pending",
    })
    return {
        "account_balance": result.get("account_balance", 0.0),
        "btc_balance": result.get("btc_balance", 0.0),
        "current_price": result.get("current_price", 0.0),
        "current_exposure": result.get("current_exposure", 0.0),
        "open_orders_count": result.get("open_orders_count", 0),
        "atr": result.get("atr", 0.0),
        "position_size": result.get("position_size", 0.0),
        "stop_loss_price": result.get("stop_loss_price", 0.0),
        "take_profit_price": result.get("take_profit_price", 0.0),
        "risk_amount": result.get("risk_amount", 0.0),
        "approved": result.get("approved", False),
        "rejection_reason": result.get("rejection_reason", ""),
        "risk_params": {
            "position_size": result.get("position_size", 0.0),
            "stop_loss_price": result.get("stop_loss_price", 0.0),
            "take_profit_price": result.get("take_profit_price", 0.0),
            "risk_amount": result.get("risk_amount", 0.0),
            "approved": result.get("approved", False),
            "rejection_reason": result.get("rejection_reason", ""),
        },
        "current_agent": "risk_manager",
        "status": result.get("status", ""),
    }


def run_executor(state: dict) -> dict:
    """Execute the Executor agent's order placement and confirmation."""
    logger.info("Orchestrator: running Executor")
    executor_graph = build_executor_graph()
    result = executor_graph.invoke({
        "signal": state["signal"],
        "risk_params": state.get("risk_params", {}),
        "dry_run": state.get("dry_run", True),
        "order_id": "",
        "fill_price": 0.0,
        "order_status": "",
        "stop_loss_order_id": "",
        "trade_record": {},
        "status": "pending",
    })
    return {
        "order_id": result.get("order_id", ""),
        "fill_price": result.get("fill_price", 0.0),
        "order_status": result.get("order_status", ""),
        "stop_loss_order_id": result.get("stop_loss_order_id", ""),
        "trade_record": result.get("trade_record", {}),
        "current_agent": "executor",
        "status": "complete",
    }


# ── Graph Builders ───────────────────────────────────────────────────

def build_analysis_graph():
    """Build the analysis pipeline: analyst -> strategist -> END"""
    graph = StateGraph(AnalysisPipelineState)

    graph.add_node("analyst", run_analyst)
    graph.add_node("strategist", run_strategist)

    graph.set_entry_point("analyst")
    graph.add_edge("analyst", "strategist")
    graph.add_edge("strategist", END)

    return graph.compile()


def build_execution_graph():
    """Build the execution pipeline: risk_manager -> executor -> END"""
    graph = StateGraph(ExecutionPipelineState)

    graph.add_node("risk_manager", run_risk_manager)
    graph.add_node("executor", run_executor)

    graph.set_entry_point("risk_manager")
    graph.add_edge("risk_manager", "executor")
    graph.add_edge("executor", END)

    return graph.compile()
