"""Standalone script to create all MongoDB indexes.

Usage:
    python -m agent_platform.db.init_indexes
"""

import asyncio

from motor.motor_asyncio import AsyncIOMotorClient

from agent_platform.config import settings
from agent_platform.db.indexes import ensure_indexes


async def main() -> None:
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB_NAME]
    print(f"Connected to {settings.MONGODB_URI} / {settings.MONGODB_DB_NAME}")
    await ensure_indexes(db)
    print("All indexes created successfully.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
