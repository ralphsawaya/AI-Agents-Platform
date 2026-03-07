"""Trading data API routes for the trading dashboard."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from agent_platform.config import settings
from agent_platform.db.client import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trading", tags=["trading"])

TRADING_CONFIG_ID = "default"


def _ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


def _err(msg: str) -> dict:
    return {"success": False, "data": None, "error": msg}


class ToggleRequest(BaseModel):
    enabled: bool


class TradingConfigUpdate(BaseModel):
    trading_enabled: bool | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    api_keys: dict | None = None
    risk_defaults: dict | None = None
    indicator_periods: dict | None = None


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
    """Toggle trading on/off (kill switch) — immediate in-memory change."""
    settings.trading_enabled = req.enabled
    state = "enabled" if req.enabled else "disabled"
    logger.info("Trading %s via kill switch", state)
    return _ok({"trading_enabled": settings.trading_enabled, "status": state})


@router.get("/config")
async def get_trading_config():
    """Get persisted trading configuration from MongoDB."""
    db = get_database()
    doc = await db["trading_config"].find_one({"_id": TRADING_CONFIG_ID})
    if not doc:
        return _ok({"trading_enabled": settings.trading_enabled})

    doc.pop("_id", None)
    doc["trading_enabled"] = settings.trading_enabled

    api_keys = doc.get("api_keys", {})
    masked: dict[str, str] = {}
    for provider, key in api_keys.items():
        if key and len(key) > 4:
            masked[provider] = "\u2022\u2022\u2022\u2022" + key[-4:]
        elif key:
            masked[provider] = "\u2022\u2022\u2022\u2022"
        else:
            masked[provider] = ""
    doc["api_keys"] = masked
    return _ok(doc)


@router.put("/config")
async def update_trading_config(body: TradingConfigUpdate):
    """Save trading configuration to MongoDB."""
    db = get_database()

    update: dict[str, Any] = {}
    if body.trading_enabled is not None:
        update["trading_enabled"] = body.trading_enabled
        settings.trading_enabled = body.trading_enabled
    if body.llm_provider is not None:
        update["llm_provider"] = body.llm_provider
    if body.llm_model is not None:
        update["llm_model"] = body.llm_model
    if body.risk_defaults is not None:
        update["risk_defaults"] = body.risk_defaults
    if body.indicator_periods is not None:
        update["indicator_periods"] = body.indicator_periods

    if body.api_keys:
        existing = await db["trading_config"].find_one({"_id": TRADING_CONFIG_ID})
        merged_keys = (existing or {}).get("api_keys", {})
        merged_keys.update(body.api_keys)
        update["api_keys"] = merged_keys

    if update:
        update["updated_at"] = datetime.now(timezone.utc)
        await db["trading_config"].update_one(
            {"_id": TRADING_CONFIG_ID},
            {"$set": update},
            upsert=True,
        )

    logger.info("Trading config saved to MongoDB: %s", list(update.keys()))
    return _ok({"updated": list(update.keys())})


class RunAnalysisRequest(BaseModel):
    agent_id: str | None = None


@router.post("/run-analysis")
async def trigger_analysis(body: RunAnalysisRequest | None = None):
    """Manually trigger the analysis pipeline."""
    db = get_database()

    agent_id = body.agent_id if body else None

    if not agent_id:
        trading_agents = await db["agents"].find(
            {"tags": "trading"},
        ).to_list(length=10)

        if not trading_agents:
            return _err("No trading agent team found (tag: 'trading')")

        agent_id = trading_agents[0]["_id"]

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
