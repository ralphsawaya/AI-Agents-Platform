from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase


class RelationshipRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._rel_col = db["agent_relationships"]
        self._tag_col = db["agent_tags"]

    # ── relationships ──

    async def upsert_relationship(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        query = {
            "source_agent_id": data["source_agent_id"],
            "target_agent_id": data["target_agent_id"],
        }
        update_fields = {
            "relationship_type": data.get("relationship_type", "calls"),
            "detected_via": data.get("detected_via", "static_analysis"),
            "confidence": data.get("confidence", 0.9),
            "created_at": now,
        }
        result = await self._rel_col.find_one_and_update(
            query,
            {"$set": update_fields, "$setOnInsert": {"_id": str(uuid4())}},
            upsert=True,
            return_document=True,
        )
        return result

    async def get_graph_data(self) -> dict[str, Any]:
        edges = await self._rel_col.find().to_list(length=1000)
        return {"edges": edges}

    async def get_agent_subgraph(self, agent_id: str) -> dict[str, Any]:
        edges = await self._rel_col.find(
            {"$or": [{"source_agent_id": agent_id}, {"target_agent_id": agent_id}]}
        ).to_list(length=200)
        return {"edges": edges}

    async def delete_by_agent(self, agent_id: str) -> int:
        result = await self._rel_col.delete_many(
            {"$or": [{"source_agent_id": agent_id}, {"target_agent_id": agent_id}]}
        )
        return result.deleted_count

    # ── tags ──

    async def upsert_tag(self, name: str, agent_id: str) -> None:
        await self._tag_col.update_one(
            {"name": name},
            {"$addToSet": {"agent_ids": agent_id}, "$setOnInsert": {"_id": str(uuid4())}},
            upsert=True,
        )

    async def remove_agent_from_tags(self, agent_id: str) -> None:
        await self._tag_col.update_many({}, {"$pull": {"agent_ids": agent_id}})

    async def list_tags(self) -> list[dict[str, Any]]:
        return await self._tag_col.find().to_list(length=200)
