from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase


class RunRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["agent_runs"]

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "_id": data.get("_id", str(uuid4())),
            "agent_id": data["agent_id"],
            "triggered_by": data.get("triggered_by", "manual"),
            "schedule_id": data.get("schedule_id"),
            "args": data.get("args", {}),
            "status": "running",
            "exit_code": None,
            "start_time": now,
            "end_time": None,
            "duration_seconds": 0.0,
            "log_path": data.get("log_path", ""),
            "error_message": None,
            "created_at": now,
        }
        await self._col.insert_one(doc)
        return doc

    async def get_by_id(self, run_id: str) -> dict[str, Any] | None:
        return await self._col.find_one({"_id": run_id})

    MAX_RUNS_RETURNED = 100

    async def list_by_agent(
        self, agent_id: str, page: int = 1, page_size: int = 15
    ) -> tuple[list[dict[str, Any]], int]:
        query = {"agent_id": agent_id}
        total = await self._col.count_documents(query)
        capped = min(total, self.MAX_RUNS_RETURNED)
        cursor = (
            self._col.find(query)
            .sort("start_time", -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        docs = await cursor.to_list(length=page_size)
        return docs, capped

    async def update_status(
        self,
        run_id: str,
        status: str,
        exit_code: int | None = None,
        error_message: str | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        fields: dict[str, Any] = {
            "status": status,
            "end_time": datetime.now(timezone.utc).isoformat(),
        }
        if exit_code is not None:
            fields["exit_code"] = exit_code
        if error_message is not None:
            fields["error_message"] = error_message
        if duration_seconds is not None:
            fields["duration_seconds"] = duration_seconds
        await self._col.update_one({"_id": run_id}, {"$set": fields})

    async def list_running(self) -> list[dict[str, Any]]:
        cursor = self._col.find({"status": "running"}).sort("start_time", -1)
        return await cursor.to_list(length=100)
