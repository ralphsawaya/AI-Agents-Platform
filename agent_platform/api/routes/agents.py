"""Agent CRUD and upload API routes."""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, File, Form, Query, UploadFile

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
async def rebuild_venv(agent_id: str):
    """Re-trigger the venv build for an agent (e.g. after a stuck or failed build)."""
    agent = await agent_manager.get_agent(agent_id)
    if not agent:
        return _err("Agent not found", 404)
    if agent.get("venv_ready"):
        return _err("Venv is already built")

    from agent_platform.db.client import get_database
    from agent_platform.db.repositories.agent_repo import AgentRepository
    repo = AgentRepository(get_database())
    await repo.update(agent_id, {"status": "idle", "venv_ready": False})

    asyncio.create_task(create_venv(agent_id, agent["upload_path"]))
    return _ok({"rebuilding": agent_id})


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str):
    deleted = await agent_manager.delete_agent(agent_id)
    if not deleted:
        return _err("Agent not found", 404)
    return _ok({"deleted": agent_id})
