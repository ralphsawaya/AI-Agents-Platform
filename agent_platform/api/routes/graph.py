"""Agent relationship graph API routes."""

import logging
from typing import Any

from fastapi import APIRouter

from agent_platform.core.graph_builder import (
    get_agent_subgraph,
    get_full_graph,
    get_team_graph,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/graph", tags=["graph"])


def _ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


def _err(msg: str, code: int = 400) -> dict:
    return {"success": False, "data": None, "error": msg}


@router.get("")
async def full_graph():
    graph = await get_full_graph()
    return _ok(graph)


@router.get("/team/{agent_id}")
async def team_graph(agent_id: str):
    """Return the internal pipeline graph for a single agent team."""
    graph = await get_team_graph(agent_id)
    if not graph:
        return _err("Team not found", 404)
    return _ok(graph)


@router.get("/agent/{agent_id}")
async def agent_subgraph(agent_id: str):
    subgraph = await get_agent_subgraph(agent_id)
    return _ok(subgraph)
