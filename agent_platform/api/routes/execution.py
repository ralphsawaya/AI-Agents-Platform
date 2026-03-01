"""Agent execution API routes — run, stop, run history."""

import logging
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from agent_platform.core.executor import execute_agent, stop_run
from agent_platform.db.client import get_database
from agent_platform.db.repositories.run_repo import RunRepository

logger = logging.getLogger(__name__)
router = APIRouter(tags=["execution"])


def _ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


def _err(msg: str) -> dict:
    return {"success": False, "data": None, "error": msg}


class RunRequest(BaseModel):
    args: dict[str, Any] = {}


@router.post("/api/agents/{agent_id}/run")
async def run_agent(agent_id: str, body: RunRequest | None = None):
    try:
        run_doc = await execute_agent(
            agent_id=agent_id,
            args=body.args if body else {},
        )
        return _ok(run_doc)
    except ValueError as exc:
        return _err(str(exc))


@router.post("/api/runs/{run_id}/stop")
async def stop_agent_run(run_id: str):
    stopped = await stop_run(run_id)
    if not stopped:
        return _err("Run not found or already finished")
    return _ok({"stopped": run_id})


@router.get("/api/agents/{agent_id}/runs")
async def list_runs(
    agent_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    db = get_database()
    repo = RunRepository(db)
    runs, total = await repo.list_by_agent(agent_id, page=page, page_size=page_size)
    return _ok({"runs": runs, "total": total, "page": page, "page_size": page_size})


@router.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    db = get_database()
    repo = RunRepository(db)
    run = await repo.get_by_id(run_id)
    if not run:
        return _err("Run not found")
    return _ok(run)


@router.get("/api/runs/{run_id}/logs")
async def get_run_logs(run_id: str):
    db = get_database()
    repo = RunRepository(db)
    run = await repo.get_by_id(run_id)
    if not run:
        return _err("Run not found")

    log_path = run.get("log_path", "")
    if not log_path:
        return _ok({"logs": ""})

    try:
        with open(log_path, "r") as f:
            content = f.read()
        return _ok({"logs": content})
    except FileNotFoundError:
        return _ok({"logs": ""})
