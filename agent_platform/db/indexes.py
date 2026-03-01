from pymongo.errors import OperationFailure

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel

from agent_platform.config import settings


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
