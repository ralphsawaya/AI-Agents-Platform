"""Trading data API routes for the trading dashboard."""

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from agent_platform.config import settings
from agent_platform.db.client import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trading", tags=["trading"])


def _ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


def _err(msg: str) -> dict:
    return {"success": False, "data": None, "error": msg}


class ToggleRequest(BaseModel):
    enabled: bool


@router.get("/regime")
async def get_current_regime():
    """Get the latest market regime classification."""
    db = get_database()
    doc = await db["market_regimes"].find_one(
        sort=[("timestamp", -1)],
    )
    if doc:
        doc["_id"] = str(doc["_id"])
    return _ok(doc)


@router.get("/risk")
async def get_risk_state():
    """Get the current risk state."""
    db = get_database()
    doc = await db["risk_state"].find_one(
        sort=[("updated_at", -1)],
    )
    if doc:
        doc["_id"] = str(doc["_id"])
    return _ok(doc)


@router.get("/signals")
async def get_recent_signals(limit: int = 20):
    """Get recent trade signals."""
    db = get_database()
    cursor = db["trade_signals"].find().sort("timestamp", -1).limit(limit)
    results = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return _ok(results)


@router.get("/trades")
async def get_recent_trades(limit: int = 20):
    """Get recent executed trades."""
    db = get_database()
    cursor = db["trades"].find().sort("timestamp", -1).limit(limit)
    results = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return _ok(results)


@router.get("/strategy-history")
async def get_strategy_history(limit: int = 10):
    """Get recent strategy selection history."""
    db = get_database()
    cursor = db["strategy_selections"].find().sort("timestamp", -1).limit(limit)
    results = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return _ok(results)


@router.post("/toggle")
async def toggle_trading(req: ToggleRequest):
    """Toggle trading on/off (kill switch)."""
    settings.trading_enabled = req.enabled
    state = "enabled" if req.enabled else "disabled"
    logger.info("Trading %s via kill switch", state)
    return _ok({"trading_enabled": settings.trading_enabled, "status": state})


@router.post("/run-analysis")
async def trigger_analysis():
    """Manually trigger the analysis pipeline."""
    db = get_database()

    trading_agents = await db["agents"].find(
        {"tags": "trading"},
    ).to_list(length=10)

    if not trading_agents:
        return _err("No trading agent team found (tag: 'trading')")

    trading_agent = trading_agents[0]
    agent_id = trading_agent["_id"]

    from agent_platform.core.executor import execute_agent

    try:
        run_doc = await execute_agent(
            agent_id=agent_id,
            args={"mode": "analysis"},
            triggered_by="manual",
        )
        return _ok({"status": "triggered", "run_id": run_doc["_id"]})
    except Exception as exc:
        return _err(str(exc)[:500])
