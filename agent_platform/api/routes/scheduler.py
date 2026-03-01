"""Schedule CRUD API routes."""

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from agent_platform.core.scheduler import scheduler_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/schedules", tags=["schedules"])


def _ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


def _err(msg: str) -> dict:
    return {"success": False, "data": None, "error": msg}


class ScheduleCreate(BaseModel):
    agent_id: str
    schedule_type: str  # cron | interval | once
    cron_expression: str | None = None
    interval_seconds: int | None = None
    run_at: str | None = None
    args: dict[str, Any] = {}
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    schedule_type: str | None = None
    cron_expression: str | None = None
    interval_seconds: int | None = None
    run_at: str | None = None
    args: dict[str, Any] | None = None
    enabled: bool | None = None


@router.post("")
async def create_schedule(body: ScheduleCreate):
    try:
        doc = await scheduler_service.add_schedule(body.model_dump())
        return _ok(doc)
    except Exception as exc:
        return _err(str(exc))


@router.get("")
async def list_all_schedules():
    schedules = await scheduler_service.list_schedules()
    return _ok(schedules)


@router.get("/agent/{agent_id}")
async def list_agent_schedules(agent_id: str):
    schedules = await scheduler_service.list_schedules(agent_id=agent_id)
    return _ok(schedules)


@router.put("/{schedule_id}")
async def update_schedule(schedule_id: str, body: ScheduleUpdate):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        return _err("No fields to update")
    success = await scheduler_service.update_schedule(schedule_id, fields)
    if not success:
        return _err("Schedule not found")
    return _ok({"updated": schedule_id})


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str):
    success = await scheduler_service.remove_schedule(schedule_id)
    if not success:
        return _err("Schedule not found")
    return _ok({"deleted": schedule_id})


@router.post("/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: str):
    from agent_platform.db.client import get_database
    from agent_platform.db.repositories.schedule_repo import ScheduleRepository

    db = get_database()
    repo = ScheduleRepository(db)
    sched = await repo.get_by_id(schedule_id)
    if not sched:
        return _err("Schedule not found")

    new_enabled = not sched.get("enabled", True)
    success = await scheduler_service.toggle_schedule(schedule_id, new_enabled)
    if not success:
        return _err("Failed to toggle schedule")
    return _ok({"schedule_id": schedule_id, "enabled": new_enabled})
