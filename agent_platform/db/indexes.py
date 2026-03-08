from pymongo.errors import CollectionInvalid, OperationFailure

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel

from agent_platform.config import settings

_OHLCV_TTL_SECONDS = 4 * 365 * 24 * 60 * 60


async def _safe_create_indexes(collection, indexes: list[IndexModel]) -> None:
    """Create indexes, dropping and recreating any that conflict due to changed options."""
    try:
        await collection.create_indexes(indexes)
    except OperationFailure as exc:
        if exc.code != 86:  # IndexKeySpecsConflict
            raise
        for idx in indexes:
            try:
                await collection.create_indexes([idx])
            except OperationFailure as inner:
                if inner.code != 86:
                    raise
                name = idx.document.get("name") or "_".join(
                    f"{k}_{v}" for k, v in idx.document["key"].items()
                )
                await collection.drop_index(name)
                await collection.create_indexes([idx])


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    agents = db["agents"]
    await _safe_create_indexes(agents, [
        IndexModel([("status", ASCENDING)]),
        IndexModel([("tags", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
    ])

    agent_runs = db["agent_runs"]
    await _safe_create_indexes(agent_runs, [
        IndexModel([("agent_id", ASCENDING), ("start_time", DESCENDING)]),
        IndexModel([("status", ASCENDING)]),
        IndexModel(
            [("created_at", ASCENDING)],
            expireAfterSeconds=settings.LOG_RETENTION_DAYS * 86400,
        ),
    ])

    schedules = db["schedules"]
    await _safe_create_indexes(schedules, [
        IndexModel([("agent_id", ASCENDING)]),
        IndexModel([("next_run_at", ASCENDING)]),
        IndexModel([("enabled", ASCENDING)]),
    ])

    relationships = db["agent_relationships"]
    await _safe_create_indexes(relationships, [
        IndexModel(
            [("source_agent_id", ASCENDING), ("target_agent_id", ASCENDING)],
            unique=True,
        ),
    ])

    # --- Trading collections ---

    market_regimes = db["market_regimes"]
    await _safe_create_indexes(market_regimes, [
        IndexModel([("timestamp", DESCENDING)]),
        IndexModel(
            [("created_at", ASCENDING)],
            expireAfterSeconds=30 * 86400,
        ),
    ])

    strategy_selections = db["strategy_selections"]
    await _safe_create_indexes(strategy_selections, [
        IndexModel([("timestamp", DESCENDING)]),
        IndexModel([("active_strategy", ASCENDING)]),
    ])

    trade_signals = db["trade_signals"]
    await _safe_create_indexes(trade_signals, [
        IndexModel([("timestamp", DESCENDING)]),
        IndexModel([("strategy_name", ASCENDING)]),
        IndexModel([("matched", ASCENDING)]),
        IndexModel(
            [("created_at", ASCENDING)],
            expireAfterSeconds=90 * 86400,
        ),
    ])

    trades = db["trades"]
    await _safe_create_indexes(trades, [
        IndexModel([("timestamp", DESCENDING)]),
        IndexModel([("status", ASCENDING)]),
        IndexModel([("side", ASCENDING)]),
    ])

    risk_state = db["risk_state"]
    await _safe_create_indexes(risk_state, [
        IndexModel([("updated_at", DESCENDING)]),
    ])

    # --- OHLCV timeseries cache (4-year TTL) ---
    try:
        await db.create_collection(
            "ohlcv",
            timeseries={
                "timeField": "timestamp",
                "metaField": "meta",
                "granularity": "minutes",
            },
            expireAfterSeconds=_OHLCV_TTL_SECONDS,
        )
    except CollectionInvalid:
        pass
