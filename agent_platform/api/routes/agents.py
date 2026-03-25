"""Agent CRUD and upload API routes."""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, File, Form, Query, UploadFile
from pydantic import BaseModel

from agent_platform.core import agent_manager
from agent_platform.core.graph_builder import build_static_graph
from agent_platform.core.venv_manager import create_venv

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["agents"])


def _ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


def _err(msg: str, status: int = 400) -> dict:
    return {"success": False, "data": None, "error": msg}


@router.post("/upload")
async def upload_agent(
    file: UploadFile = File(...),
    name: str = Form(None),
    description: str = Form(""),
    tags: str = Form(""),
):
    """Upload a .zip agent package, validate, and register it."""
    if not file.filename or not file.filename.endswith(".zip"):
        return _err("Only .zip files are accepted")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        return _err("Uploaded file is empty")

    try:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        doc = await agent_manager.register_agent(
            file_bytes=file_bytes,
            filename=file.filename,
            name=name,
            description=description,
            tags=tag_list,
        )
    except ValueError as exc:
        return _err(str(exc))

    # Fire-and-forget: build venv and run static analysis in background
    asyncio.create_task(create_venv(doc["_id"], doc["upload_path"]))
    asyncio.create_task(build_static_graph(doc["_id"]))

    return _ok(doc)


@router.get("")
async def list_agents(
    status: str | None = Query(None),
    tags: str | None = Query(None),
    name: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    agents = await agent_manager.list_agents(
        status=status, tags=tag_list, name=name,
        date_from=date_from, date_to=date_to,
    )
    return _ok(agents)


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    agent = await agent_manager.get_agent(agent_id)
    if not agent:
        return _err("Agent not found", 404)
    return _ok(agent)


@router.get("/{agent_id}/files")
async def get_file_tree(agent_id: str):
    tree = agent_manager.get_file_tree(agent_id)
    if tree is None:
        return _err("Agent not found or no files", 404)
    return _ok(tree)


@router.get("/{agent_id}/files/{file_path:path}")
async def get_file_content(agent_id: str, file_path: str):
    content = agent_manager.get_file_content(agent_id, file_path)
    if content is None:
        return _err("File not found", 404)
    return _ok({"path": file_path, "content": content})


@router.post("/{agent_id}/rebuild")
async def rebuild_venv(agent_id: str, force: bool = Query(False)):
    """Re-trigger the venv build for an agent (e.g. after a stuck or failed build).

    Pass ?force=true to rebuild even when the venv is already ready.
    """
    agent = await agent_manager.get_agent(agent_id)
    if not agent:
        return _err("Agent not found", 404)
    if agent.get("venv_ready") and not force:
        return _err("Venv is already built — use ?force=true to rebuild anyway")

    from agent_platform.db.client import get_database
    from agent_platform.db.repositories.agent_repo import AgentRepository
    repo = AgentRepository(get_database())
    await repo.update(agent_id, {"status": "idle", "venv_ready": False})

    asyncio.create_task(create_venv(agent_id, agent["upload_path"]))
    return _ok({"rebuilding": agent_id})


class AgentMetadataUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None


@router.put("/{agent_id}/metadata")
async def update_agent_metadata(agent_id: str, body: AgentMetadataUpdate):
    """Update an agent's name, description, and/or tags."""
    agent = await agent_manager.get_agent(agent_id)
    if not agent:
        return _err("Agent not found", 404)

    fields: dict[str, Any] = {}
    if body.name is not None:
        name = body.name.strip()
        if not name:
            return _err("Name cannot be empty")
        fields["name"] = name
    if body.description is not None:
        fields["description"] = body.description
    if body.tags is not None:
        fields["tags"] = [t.strip() for t in body.tags if t.strip()]

    if not fields:
        return _ok(agent)

    from agent_platform.db.client import get_database
    from agent_platform.db.repositories.agent_repo import AgentRepository
    from agent_platform.db.repositories.relationship_repo import RelationshipRepository

    repo = AgentRepository(get_database())
    await repo.update(agent_id, fields)

    if "tags" in fields:
        rel_repo = RelationshipRepository(get_database())
        await rel_repo.remove_agent_from_tags(agent_id)
        for tag in fields["tags"]:
            await rel_repo.upsert_tag(tag, agent_id)

    updated = await repo.get_by_id(agent_id)
    return _ok(updated)


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str):
    deleted = await agent_manager.delete_agent(agent_id)
    if not deleted:
        return _err("Agent not found", 404)
    return _ok({"deleted": agent_id})
