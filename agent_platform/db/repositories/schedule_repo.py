from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase


class ScheduleRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["schedules"]

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "_id": data.get("_id", str(uuid4())),
            "agent_id": data["agent_id"],
            "schedule_type": data["schedule_type"],
            "cron_expression": data.get("cron_expression"),
            "interval_seconds": data.get("interval_seconds"),
            "run_at": data.get("run_at"),
            "args": data.get("args", {}),
            "enabled": data.get("enabled", True),
            "next_run_at": data.get("next_run_at"),
            "created_at": now,
        }
        await self._col.insert_one(doc)
        return doc

    async def get_by_id(self, schedule_id: str) -> dict[str, Any] | None:
        return await self._col.find_one({"_id": schedule_id})

    async def list_by_agent(self, agent_id: str) -> list[dict[str, Any]]:
        cursor = self._col.find({"agent_id": agent_id}).sort("created_at", -1)
        return await cursor.to_list(length=100)

    async def list_all(self) -> list[dict[str, Any]]:
        cursor = self._col.find().sort("created_at", -1)
        return await cursor.to_list(length=500)

    async def list_enabled(self) -> list[dict[str, Any]]:
        cursor = self._col.find({"enabled": True})
        return await cursor.to_list(length=500)

    async def update(self, schedule_id: str, fields: dict[str, Any]) -> bool:
        result = await self._col.update_one({"_id": schedule_id}, {"$set": fields})
        return result.modified_count > 0

    async def delete(self, schedule_id: str) -> bool:
        result = await self._col.delete_one({"_id": schedule_id})
        return result.deleted_count > 0

    async def toggle_enabled(self, schedule_id: str, enabled: bool) -> bool:
        return await self.update(schedule_id, {"enabled": enabled})

    async def delete_by_agent(self, agent_id: str) -> int:
        result = await self._col.delete_many({"agent_id": agent_id})
        return result.deleted_count
