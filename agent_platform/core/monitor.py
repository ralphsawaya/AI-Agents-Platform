"""Real-time monitoring service.

Polls psutil every 2 seconds for CPU/memory of running agent subprocesses,
broadcasts metrics over WebSocket, and checks the consecutive failure
threshold to surface alerts.
"""

import asyncio
import logging
import time
from typing import Any

import psutil

from agent_platform.config import settings
from agent_platform.core.executor import get_active_runs
from agent_platform.core.ws_manager import ws_manager
from agent_platform.db.client import get_database
from agent_platform.db.repositories.agent_repo import AgentRepository
from agent_platform.db.repositories.run_repo import RunRepository

logger = logging.getLogger(__name__)


class MonitorService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._poll_loop())
            logger.info("Monitor service started")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("Monitor service stopped")

    async def _poll_loop(self) -> None:
        """Continuously poll resource usage of active runs every 2 seconds."""
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Monitor poll error")
            await asyncio.sleep(2)

    async def _poll_once(self) -> None:
        active = get_active_runs()
        if not active:
            return

        snapshot: list[dict[str, Any]] = []

        for run_id, info in list(active.items()):
            pid = info["pid"]
            agent_id = info["agent_id"]
            agent_name = info.get("agent_name", "unknown")
            start = info["start"]
            elapsed = time.time() - start

            try:
                proc = psutil.Process(pid)
                cpu = proc.cpu_percent(interval=0)
                mem = proc.memory_info().rss / (1024 * 1024)  # MB
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                cpu = 0.0
                mem = 0.0

            # Read last log line
            last_line = ""
            try:
                db = get_database()
                run_repo = RunRepository(db)
                run_doc = await run_repo.get_by_id(run_id)
                if run_doc and run_doc.get("log_path"):
                    try:
                        with open(run_doc["log_path"], "rb") as f:
                            f.seek(0, 2)
                            size = f.tell()
                            read_size = min(size, 500)
                            f.seek(max(0, size - read_size))
                            tail = f.read().decode(errors="replace")
                            lines = tail.strip().splitlines()
                            last_line = lines[-1] if lines else ""
                    except FileNotFoundError:
                        pass
            except Exception:
                pass

            # Broadcast per-run metrics
            await ws_manager.broadcast_metrics(run_id, cpu, mem, elapsed)

            snapshot.append({
                "run_id": run_id,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "pid": pid,
                "cpu_percent": cpu,
                "memory_mb": round(mem, 1),
                "elapsed_seconds": round(elapsed, 1),
                "last_log_line": last_line[:200],
            })

        # Broadcast global monitor snapshot
        if snapshot:
            await ws_manager.broadcast_monitor({"type": "monitor", "runs": snapshot})

    async def get_running_snapshot(self) -> list[dict[str, Any]]:
        """Return current resource usage for all active runs (REST endpoint)."""
        active = get_active_runs()
        result: list[dict[str, Any]] = []

        db = get_database()
        agent_repo = AgentRepository(db)

        for run_id, info in list(active.items()):
            pid = info["pid"]
            agent_id = info["agent_id"]
            elapsed = time.time() - info["start"]

            try:
                proc = psutil.Process(pid)
                cpu = proc.cpu_percent(interval=0)
                mem = proc.memory_info().rss / (1024 * 1024)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                cpu = 0.0
                mem = 0.0

            agent = await agent_repo.get_by_id(agent_id)
            agent_name = agent["name"] if agent else "unknown"

            result.append({
                "run_id": run_id,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "pid": pid,
                "cpu_percent": round(cpu, 1),
                "memory_mb": round(mem, 1),
                "elapsed_seconds": round(elapsed, 1),
            })

        return result

    async def get_alerts(self) -> list[dict[str, Any]]:
        """Return agents that have exceeded the consecutive failure threshold."""
        db = get_database()
        agent_repo = AgentRepository(db)
        agents = await agent_repo.list_all(status="error")
        return [
            {
                "agent_id": a["_id"],
                "name": a["name"],
                "consecutive_failures": a.get("consecutive_failures", 0),
            }
            for a in agents
            if a.get("consecutive_failures", 0) >= settings.FAILURE_ALERT_THRESHOLD
        ]


monitor_service = MonitorService()
