"""APScheduler integration with MongoDB job store.

Supports cron, interval, and one-time schedules. All job state is persisted
in MongoDB so schedules survive platform restarts.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import MongoClient

from agent_platform.config import settings
from agent_platform.db.repositories.schedule_repo import ScheduleRepository

logger = logging.getLogger(__name__)

_main_loop: asyncio.AbstractEventLoop | None = None


def _run_agent_sync(agent_id: str, args: dict, schedule_id: str) -> None:
    """Synchronous wrapper called by APScheduler from a thread-pool thread.

    Uses run_coroutine_threadsafe to schedule the async executor on the
    main event loop since APScheduler dispatches sync jobs in a ThreadPool
    where no event loop exists.
    """
    from agent_platform.core.executor import execute_agent

    if _main_loop is None or _main_loop.is_closed():
        logger.error("Cannot run scheduled agent — main event loop not available")
        return

    asyncio.run_coroutine_threadsafe(
        execute_agent(
            agent_id=agent_id,
            args=args,
            triggered_by="scheduler",
            schedule_id=schedule_id,
        ),
        _main_loop,
    )


class SchedulerService:
    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None
        self._db: AsyncIOMotorDatabase | None = None

    async def start(self, db: AsyncIOMotorDatabase) -> None:
        global _main_loop
        _main_loop = asyncio.get_running_loop()
        self._db = db

        # APScheduler's MongoDBJobStore uses synchronous pymongo
        sync_client = MongoClient(settings.MONGODB_URI)
        jobstore = MongoDBJobStore(
            database=settings.MONGODB_DB_NAME,
            collection="apscheduler_jobs",
            client=sync_client,
        )

        self._scheduler = AsyncIOScheduler(
            jobstores={"default": jobstore},
            job_defaults={"coalesce": True, "max_instances": 1},
        )
        self._scheduler.start()
        logger.info("APScheduler started with MongoDBJobStore")

        # Reload persisted schedules
        await self._reload_schedules()

    async def shutdown(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            logger.info("APScheduler shut down")

    async def _reload_schedules(self) -> None:
        """Load all enabled schedules from DB and ensure they have APScheduler jobs."""
        if self._db is None:
            return
        repo = ScheduleRepository(self._db)
        schedules = await repo.list_enabled()
        for sched in schedules:
            try:
                self._ensure_job(sched)
            except Exception:
                logger.exception("Failed to reload schedule %s", sched["_id"])

    def _build_trigger(self, sched: dict[str, Any]):
        stype = sched["schedule_type"]
        if stype == "cron":
            return CronTrigger.from_crontab(sched["cron_expression"])
        elif stype == "interval":
            return IntervalTrigger(seconds=sched["interval_seconds"])
        elif stype == "once":
            run_at = sched.get("run_at")
            if isinstance(run_at, str):
                run_at = datetime.fromisoformat(run_at)
            return DateTrigger(run_date=run_at)
        else:
            raise ValueError(f"Unknown schedule type: {stype}")

    def _ensure_job(self, sched: dict[str, Any]) -> None:
        if not self._scheduler:
            return
        job_id = sched["_id"]
        trigger = self._build_trigger(sched)

        # Remove existing job if present, then re-add
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

        self._scheduler.add_job(
            _run_agent_sync,
            trigger=trigger,
            id=job_id,
            args=[sched["agent_id"], sched.get("args", {}), sched["_id"]],
            replace_existing=True,
        )

    async def add_schedule(self, sched_doc: dict[str, Any]) -> dict[str, Any]:
        if self._db is None:
            raise RuntimeError("Scheduler not started")
        repo = ScheduleRepository(self._db)
        doc = await repo.create(sched_doc)
        self._ensure_job(doc)
        await self._update_next_run(doc["_id"])
        logger.info("Schedule %s added for agent %s", doc["_id"], doc["agent_id"])
        return doc

    async def remove_schedule(self, schedule_id: str) -> bool:
        if self._db is None:
            return False
        repo = ScheduleRepository(self._db)
        if self._scheduler:
            try:
                self._scheduler.remove_job(schedule_id)
            except Exception:
                pass
        return await repo.delete(schedule_id)

    async def toggle_schedule(self, schedule_id: str, enabled: bool) -> bool:
        if self._db is None:
            return False
        repo = ScheduleRepository(self._db)
        success = await repo.toggle_enabled(schedule_id, enabled)
        if not success:
            return False

        if enabled:
            sched = await repo.get_by_id(schedule_id)
            if sched:
                self._ensure_job(sched)
                await self._update_next_run(schedule_id)
        else:
            if self._scheduler:
                try:
                    self._scheduler.remove_job(schedule_id)
                except Exception:
                    pass
        return True

    async def update_schedule(
        self, schedule_id: str, fields: dict[str, Any]
    ) -> bool:
        if self._db is None:
            return False
        repo = ScheduleRepository(self._db)
        success = await repo.update(schedule_id, fields)
        if not success:
            return False

        sched = await repo.get_by_id(schedule_id)
        if sched and sched.get("enabled"):
            self._ensure_job(sched)
            await self._update_next_run(schedule_id)
        return True

    async def _update_next_run(self, schedule_id: str) -> None:
        """Compute and persist the next run time from APScheduler."""
        if self._scheduler is None or self._db is None:
            return
        try:
            job = self._scheduler.get_job(schedule_id)
            if job and job.next_run_time:
                repo = ScheduleRepository(self._db)
                await repo.update(
                    schedule_id,
                    {"next_run_at": job.next_run_time.isoformat()},
                )
        except Exception:
            pass

    async def list_schedules(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        if self._db is None:
            return []
        repo = ScheduleRepository(self._db)
        if agent_id:
            return await repo.list_by_agent(agent_id)
        return await repo.list_all()


scheduler_service = SchedulerService()
