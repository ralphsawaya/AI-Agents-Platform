"""TradingView webhook endpoint for receiving trade signals."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agent_platform.config import settings
from agent_platform.db.client import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhook", tags=["webhook"])

VALID_ACTIONS = {"buy", "sell", "close", "close_buy", "close_sell"}
VALID_STRATEGIES = {"trend_following", "mean_reversion", "scalping"}


class TradingViewAlert(BaseModel):
    secret: str = ""
    strategy_name: str
    action: str
    ticker: str = "BTCUSDT"
    price: str = "0"
    time: str = ""


async def _get_active_strategy(db) -> str | None:
    """Return the currently active strategy name, or None."""
    doc = await db["strategy_selections"].find_one(
        sort=[("timestamp", -1)],
    )
    return doc["active_strategy"] if doc else None


async def _count_today_trades(db) -> int:
    """Count trades executed today."""
    start_of_day = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    return await db["trades"].count_documents(
        {"timestamp": {"$gte": start_of_day}},
    )


async def _is_duplicate_signal(db, strategy_name: str, action: str) -> bool:
    """Check if an identical signal was received within the duplicate window."""
    window_seconds = settings.trading_duplicate_window_seconds
    cutoff = datetime.now(timezone.utc).timestamp() - window_seconds
    cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
    existing = await db["trade_signals"].find_one({
        "strategy_name": strategy_name,
        "action": action,
        "timestamp": {"$gte": cutoff_dt},
    })
    return existing is not None


@router.post("/tradingview")
async def tradingview_webhook(request: Request) -> dict[str, Any]:
    """Receive and process a TradingView webhook alert.

    1. Validate the shared secret
    2. Check if trading is enabled (kill switch)
    3. Parse the signal
    4. Check for duplicate signals
    5. Match against active strategy
    6. If matched, trigger the execution pipeline
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    alert = TradingViewAlert(**body)

    if settings.tradingview_webhook_secret:
        if alert.secret != settings.tradingview_webhook_secret:
            logger.warning("Webhook received with invalid secret")
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    if not settings.trading_enabled:
        logger.info("Trading is disabled (kill switch). Signal ignored.")
        return {"status": "rejected", "reason": "trading_disabled"}

    action = alert.action.lower()
    if action not in VALID_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action '{alert.action}'. Must be one of: {VALID_ACTIONS}",
        )

    if alert.strategy_name not in VALID_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy '{alert.strategy_name}'. Must be one of: {VALID_STRATEGIES}",
        )

    db = get_database()

    if await _is_duplicate_signal(db, alert.strategy_name, action):
        logger.info("Duplicate signal ignored: %s / %s", alert.strategy_name, action)
        return {"status": "rejected", "reason": "duplicate_signal"}

    active_strategy = await _get_active_strategy(db)
    matched = active_strategy == alert.strategy_name

    try:
        price = float(alert.price)
    except (ValueError, TypeError):
        price = 0.0

    signal_doc = {
        "strategy_name": alert.strategy_name,
        "action": action,
        "ticker": alert.ticker,
        "price": price,
        "matched": matched,
        "active_strategy": active_strategy,
        "raw_time": alert.time,
        "timestamp": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
    }
    await db["trade_signals"].insert_one(signal_doc)

    if not matched:
        logger.info(
            "Signal from '%s' ignored — active strategy is '%s'",
            alert.strategy_name,
            active_strategy,
        )
        return {
            "status": "ignored",
            "reason": "strategy_mismatch",
            "signal_strategy": alert.strategy_name,
            "active_strategy": active_strategy,
        }

    today_count = await _count_today_trades(db)
    if today_count >= settings.trading_max_daily_trades:
        logger.warning("Daily trade limit reached (%d)", today_count)
        return {"status": "rejected", "reason": "daily_limit_reached"}

    # Trigger execution pipeline via the agent team
    from agent_platform.core.executor import execute_agent
    from agent_platform.db.repositories.agent_repo import AgentRepository

    agent_repo = AgentRepository(db)

    trading_agents = await db["agents"].find(
        {"tags": "trading"},
    ).to_list(length=10)

    if not trading_agents:
        logger.error("No trading agent team found (tag: 'trading')")
        return {"status": "error", "reason": "no_trading_agent"}

    trading_agent = trading_agents[0]
    agent_id = trading_agent["_id"]

    execution_args = {
        "mode": "execution",
        "signal": {
            "strategy_name": alert.strategy_name,
            "action": action,
            "ticker": alert.ticker,
            "price": price,
        },
        "dry_run": settings.trading_dry_run,
    }

    try:
        run_doc = await execute_agent(
            agent_id=agent_id,
            args=execution_args,
            triggered_by="webhook",
        )
        logger.info(
            "Execution pipeline triggered: run_id=%s, signal=%s/%s",
            run_doc["_id"],
            alert.strategy_name,
            action,
        )
        return {
            "status": "executed",
            "run_id": run_doc["_id"],
            "signal": alert.strategy_name,
            "action": action,
        }
    except Exception as exc:
        logger.exception("Failed to trigger execution pipeline: %s", exc)
        return {"status": "error", "reason": str(exc)[:500]}


@router.get("/tradingview/status")
async def webhook_status() -> dict[str, Any]:
    """Return current trading system status."""
    db = get_database()

    active_strategy = await _get_active_strategy(db)
    today_trades = await _count_today_trades(db)

    regime_doc = await db["market_regimes"].find_one(
        sort=[("timestamp", -1)],
    )

    return {
        "success": True,
        "data": {
            "trading_enabled": settings.trading_enabled,
            "dry_run": settings.trading_dry_run,
            "active_strategy": active_strategy,
            "current_regime": regime_doc.get("regime") if regime_doc else None,
            "today_trades": today_trades,
            "max_daily_trades": settings.trading_max_daily_trades,
        },
        "error": None,
    }
