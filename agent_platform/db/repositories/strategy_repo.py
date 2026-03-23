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


# Seeded strategies — only used to populate MongoDB on startup.
# `_builtin_id` is an internal upsert key so restarts don't create duplicates.
_SEED_META: list[dict] = [
    {
        "_builtin_id": "scalping",
        "name": "Scalping (EMA + VWAP + Volume)",
        "timeframe": "15m",
        "description": (
            "Entry on price > VWAP AND price > EMA with volume spike and RSI > 50. "
            "ATR-based stop-loss and take-profit."
        ),
        "strategy_rules": (
            "LONG  : price > VWAP AND price > EMA\n"
            "        AND volume > volMA \u00d7 threshold\n"
            "        AND RSI > 50\n"
            "EXIT  : price < VWAP OR price < EMA\n"
            "SL/TP : ATR-based dynamic levels"
        ),
        "pine_file": "scalping.pine",
    },
    {
        "_builtin_id": "trend_following",
        "name": "Trend Following (EMA Cross + ADX)",
        "timeframe": "4h",
        "description": (
            "Bullish EMA crossover + ADX above threshold + MACD histogram confirmation. "
            "ATR trailing stop exit."
        ),
        "strategy_rules": (
            "LONG  : EMA(fast) crosses above EMA(mid)\n"
            "        AND ADX > threshold\n"
            "        AND MACD histogram > 0\n"
            "EXIT  : bearish cross OR trailing stop hit\n"
            "TRAIL : high \u2212 ATR \u00d7 multiplier"
        ),
        "pine_file": "trend_following.pine",
    },
    {
        "_builtin_id": "mean_reversion",
        "name": "Mean Reversion (BB + RSI)",
        "timeframe": "4h",
        "description": (
            "Buy at lower Bollinger Band when RSI is oversold and volume confirms. "
            "Exit at middle or upper BB."
        ),
        "strategy_rules": (
            "LONG  : price \u2264 lower BB\n"
            "        AND RSI < oversold level\n"
            "        AND volume > volMA \u00d7 1.5\n"
            "EXIT  : price \u2265 upper BB AND RSI > overbought\n"
            "TP    : price reaches middle BB (mean)\n"
            "SL    : entry \u2212 ATR \u00d7 1.5"
        ),
        "pine_file": "mean_reversion.pine",
    },
]

_COLLECTION = "backtest_strategies"


async def seed_builtin_strategies() -> None:
    """Upsert the three default strategies on startup.

    The `_builtin_id` field is an internal seeding key only — it is NOT
    exposed through the API and carries no special protection.
    """
    db = get_database()
    now = datetime.now(timezone.utc)
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
    # Try ObjectId first (user-created strategies)
    try:
        oid = ObjectId(strategy_id)
        result = await db[_COLLECTION].delete_one({"_id": oid})
        if result.deleted_count > 0:
            return True
    except Exception:
        pass
    # Fall back to _builtin_id (seeded strategies)
    result = await db[_COLLECTION].delete_one({"_builtin_id": strategy_id})
    return result.deleted_count > 0
