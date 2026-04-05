"""Repository for backtest strategies (Pine Script, stored in MongoDB)."""

from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId

from agent_platform.db.client import get_database

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PINE_DIR = _REPO_ROOT / "teams" / "trading_agents" / "strategies"


def _read_pine(filename: str) -> str:
    try:
        return (_PINE_DIR / filename).read_text(encoding="utf-8")
    except Exception:
        return ""


_SEED_META: list[dict] = [
    {
        "_builtin_id": "ema_trend",
        "name": "EMA Trend (4H) — WF Validated",
        "timeframe": "4h",
        "description": (
            "Pure EMA crossover trend strategy with ATR trailing stop. "
            "Only 3 parameters (ema_fast, ema_slow, atr_trail). Walk-forward "
            "validated: OOS Sharpe 1.19, +64.6% return, positive all years. "
            "408% WF efficiency — anti-fragile."
        ),
        "strategy_rules": (
            "LONG  : EMA(fast) crosses above EMA(slow)\n"
            "EXIT  : ATR trailing stop OR opposite EMA cross\n"
            "SHORT : EMA(fast) crosses below EMA(slow)\n"
            "EXIT  : ATR trailing stop OR opposite EMA cross\n"
            "NOTE  : Flips directly from long to short on cross"
        ),
        "pine_file": "ema_trend.pine",
    },
    {
        "_builtin_id": "rsi_momentum",
        "name": "RSI Momentum (4H) — WF Validated",
        "timeframe": "4h",
        "description": (
            "RSI 50-line crossover with EMA trend confirmation, trail-only exit. "
            "Only 3 parameters (rsi_len, ema_len, atr_trail). Walk-forward "
            "validated: OOS Sharpe 1.37, +88.5% return, positive all years. "
            "124% WF efficiency."
        ),
        "strategy_rules": (
            "LONG  : RSI crosses above 50 AND close > EMA\n"
            "SHORT : RSI crosses below 50 AND close < EMA\n"
            "EXIT  : ATR trailing stop ONLY (no opposite signal exit)"
        ),
        "pine_file": "rsi_momentum.pine",
    },
    {
        "_builtin_id": "macd_trend",
        "name": "MACD Trend (4H) — WF Validated",
        "timeframe": "4h",
        "description": (
            "MACD histogram sign-change with EMA trend filter, trail-only exit. "
            "Only 3 parameters (macd_fast, macd_slow, atr_trail). "
            "OOS Sharpe 1.25, +80.3% return, 242% WF efficiency."
        ),
        "strategy_rules": (
            "LONG  : MACD histogram turns positive AND close > EMA(slow)\n"
            "SHORT : MACD histogram turns negative AND close < EMA(slow)\n"
            "EXIT  : ATR trailing stop ONLY (no opposite signal exit)"
        ),
        "pine_file": "macd_trend.pine",
    },
]

_COLLECTION = "backtest_strategies"

_DEPRECATED_BUILTIN_IDS = [
    "scalping", "breakout", "accumulation",
    "trend_following", "mean_reversion", "swing_momentum", "pullback",
]


async def seed_builtin_strategies() -> None:
    """Upsert the four default strategies on startup and clean deprecated ones.

    The `_builtin_id` field is an internal seeding key only — it is NOT
    exposed through the API and carries no special protection.
    """
    db = get_database()
    now = datetime.now(timezone.utc)

    for old_id in _DEPRECATED_BUILTIN_IDS:
        await db[_COLLECTION].delete_many({"_builtin_id": old_id})

    for meta in _SEED_META:
        pine_script = _read_pine(meta["pine_file"])
        await db[_COLLECTION].update_one(
            {"_builtin_id": meta["_builtin_id"]},
            {
                "$set": {
                    "_builtin_id": meta["_builtin_id"],
                    "name": meta["name"],
                    "timeframe": meta["timeframe"],
                    "description": meta["description"],
                    "strategy_rules": meta["strategy_rules"],
                    "pine_script": pine_script,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )


def _doc_to_dict(doc: dict) -> dict:
    """Normalise a MongoDB document to the API shape."""
    return {
        "id": doc.get("_builtin_id") or str(doc["_id"]),
        "name": doc["name"],
        "timeframe": doc.get("timeframe", "4h"),
        "description": doc.get("description", ""),
        "strategy_rules": doc.get("strategy_rules", ""),
        "pine_script": doc.get("pine_script", ""),
        "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None,
    }


async def list_strategies() -> list[dict]:
    """Return all strategies sorted by creation date."""
    db = get_database()
    docs = await db[_COLLECTION].find({}).sort("created_at", 1).to_list(None)
    return [_doc_to_dict(d) for d in docs]


async def create_strategy(
    name: str,
    timeframe: str,
    description: str,
    strategy_rules: str,
    pine_script: str,
) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    doc = {
        "name": name,
        "timeframe": timeframe,
        "description": description,
        "strategy_rules": strategy_rules,
        "pine_script": pine_script,
        "created_at": now,
    }
    result = await db[_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_dict(doc)


async def delete_strategy(strategy_id: str) -> bool:
    """Delete any strategy by its exposed `id`.

    Seeded strategies use their `_builtin_id` string as their id;
    user-created strategies use their MongoDB ObjectId string.
    """
    db = get_database()
    try:
        oid = ObjectId(strategy_id)
        result = await db[_COLLECTION].delete_one({"_id": oid})
        if result.deleted_count > 0:
            return True
    except Exception:
        pass
    result = await db[_COLLECTION].delete_one({"_builtin_id": strategy_id})
    return result.deleted_count > 0
