"""Agent relationship graph API routes."""

import logging
from typing import Any

from fastapi import APIRouter

from agent_platform.core.graph_builder import get_agent_subgraph, get_full_graph

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/graph", tags=["graph"])


def _ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


@router.get("")
async def full_graph():
    graph = await get_full_graph()
    return _ok(graph)


@router.get("/agent/{agent_id}")
async def agent_subgraph(agent_id: str):
    subgraph = await get_agent_subgraph(agent_id)
    return _ok(subgraph)
