from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase


class AgentRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["agents"]

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "_id": data.get("_id", str(uuid4())),
            "name": data["name"],
            "description": data.get("description", ""),
            "tags": data.get("tags", []),
            "status": "idle",
            "entry_point": data.get("entry_point", "orchestrator/main.py"),
            "root_folder": data.get("root_folder", ""),
            "agent_folders": data.get("agent_folders", []),
            "has_orchestrator": data.get("has_orchestrator", True),
            "upload_path": data.get("upload_path", ""),
            "venv_path": data.get("venv_path", ""),
            "venv_ready": False,
            "source_structure": data.get("source_structure", {}),
            "detected_nodes": data.get("detected_nodes", []),
            "detected_tools": data.get("detected_tools", []),
            "nodes_by_agent": data.get("nodes_by_agent", {}),
            "tools_by_agent": data.get("tools_by_agent", {}),
            "run_count": 0,
            "consecutive_failures": 0,
            "last_run_at": None,
            "created_at": now,
            "updated_at": now,
        }
        if data.get("run_config"):
            doc["run_config"] = data["run_config"]
        if data.get("custom_tabs"):
            doc["custom_tabs"] = data["custom_tabs"]
        await self._col.insert_one(doc)
        return doc

    async def get_by_id(self, agent_id: str) -> dict[str, Any] | None:
        return await self._col.find_one({"_id": agent_id})

    async def list_all(
        self,
        status: str | None = None,
        tags: list[str] | None = None,
        name: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        if tags:
            query["tags"] = {"$all": tags}
        if name:
            query["name"] = {"$regex": name, "$options": "i"}
        if date_from or date_to:
            date_q: dict[str, str] = {}
            if date_from:
                date_q["$gte"] = date_from
            if date_to:
                date_q["$lte"] = date_to
            query["created_at"] = date_q
        cursor = self._col.find(query).sort("created_at", -1)
        return await cursor.to_list(length=500)

    async def update(self, agent_id: str, fields: dict[str, Any]) -> bool:
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = await self._col.update_one({"_id": agent_id}, {"$set": fields})
        return result.modified_count > 0

    async def delete(self, agent_id: str) -> bool:
        result = await self._col.delete_one({"_id": agent_id})
        return result.deleted_count > 0

    async def increment_run_count(self, agent_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._col.update_one(
            {"_id": agent_id},
            {"$inc": {"run_count": 1}, "$set": {"last_run_at": now, "updated_at": now}},
        )

    async def set_status(self, agent_id: str, status: str) -> None:
        await self.update(agent_id, {"status": status})

    async def update_consecutive_failures(self, agent_id: str, reset: bool = False) -> int:
        if reset:
            await self.update(agent_id, {"consecutive_failures": 0})
            return 0
        result = await self._col.find_one_and_update(
            {"_id": agent_id},
            {
                "$inc": {"consecutive_failures": 1},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
            },
            return_document=True,
        )
        return result["consecutive_failures"] if result else 0
