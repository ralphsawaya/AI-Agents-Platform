from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from agent_platform.config import settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    global _client, _db
    _client = AsyncIOMotorClient(settings.MONGODB_URI)
    _db = _client[settings.MONGODB_DB_NAME]
    await _client.admin.command("ping")


async def close_db() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None


def get_database() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not initialised – call connect_db() first")
    return _db
