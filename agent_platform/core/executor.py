"""Isolated agent execution engine.

Spawns each agent run as a subprocess inside the agent's extracted folder
using its dedicated venv.  Streams stdout/stderr to a log file and over
WebSocket in real-time.  Supports configurable timeouts and SIGTERM-based
stop.
"""

import asyncio
import json
import logging
import os
import signal
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_platform.config import settings
from agent_platform.core.ws_manager import ws_manager
from agent_platform.db.client import get_database
from agent_platform.db.repositories.agent_repo import AgentRepository
from agent_platform.db.repositories.run_repo import RunRepository

logger = logging.getLogger(__name__)

# run_id -> {"pid": int, "process": Process, "agent_id": str, "start": float}
_active_runs: dict[str, dict[str, Any]] = {}


def get_active_runs() -> dict[str, dict[str, Any]]:
    return _active_runs


async def execute_agent(
    agent_id: str,
    args: dict[str, Any] | None = None,
    triggered_by: str = "manual",
    schedule_id: str | None = None,
) -> dict[str, Any]:
    """Launch an agent run as an isolated subprocess.

    1. Guards against running agents whose venv is not ready.
    2. Creates the run document in MongoDB.
    3. Spawns <venv>/bin/python orchestrator/main.py inside the agent's folder.
    4. Streams output to a log file AND broadcasts lines over WebSocket.
    5. On completion, updates the run document with exit code and duration.
    """
    db = get_database()
    agent_repo = AgentRepository(db)
    run_repo = RunRepository(db)

    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")
    if not agent.get("venv_ready"):
        raise ValueError(
            f"Agent {agent_id} venv is not ready — wait for build to finish"
        )

    run_id = str(uuid4())
    upload_path = Path(agent["upload_path"])

    # Resolve the root folder inside the extraction dir
    if agent.get("root_folder"):
        root_dir = upload_path / agent["root_folder"]
    else:
        platform_dirs = {".venv", "logs"}
        root_dirs = [d for d in upload_path.iterdir() if d.is_dir() and d.name not in platform_dirs and not d.name.startswith(".")]
        root_dir = root_dirs[0] if root_dirs else upload_path

    log_dir = upload_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{run_id}.log"

    venv_python = Path(agent["venv_path"]) / "bin" / "python"
    if not venv_python.exists():
        venv_python = Path(agent["venv_path"]) / "Scripts" / "python.exe"

    entry_point = root_dir / agent.get("entry_point", "orchestrator/main.py")

    run_doc = await run_repo.create({
        "_id": run_id,
        "agent_id": agent_id,
        "triggered_by": triggered_by,
        "schedule_id": schedule_id,
        "args": args or {},
        "log_path": str(log_path),
    })

    await agent_repo.set_status(agent_id, "running")

    env = os.environ.copy()
    env["AGENT_ID"] = agent_id
    env["AGENT_RUN_ID"] = run_id
    env["AGENT_ARGS"] = json.dumps(args or {})

    # Load the team's own .env file if it exists in the agent root directory
    team_env_path = root_dir / ".env"
    if team_env_path.exists():
        logger.info("Loading team .env from %s", team_env_path)
        for line in team_env_path.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, _, value = stripped.partition("=")
                key = key.strip()
                value = value.strip()
                if key and value and value != "PLATFORM_MANAGED":
                    env[key] = value

    timeout = agent.get("timeout_seconds", settings.DEFAULT_TIMEOUT_SECONDS)

    # Fire-and-forget: the streaming task runs in background
    asyncio.create_task(_run_subprocess(
        run_id=run_id,
        agent_id=agent_id,
        agent_name=agent.get("name", "unknown"),
        venv_python=str(venv_python),
        entry_point=str(entry_point),
        cwd=str(root_dir),
        env=env,
        log_path=log_path,
        timeout=timeout,
    ))

    return run_doc


async def _run_subprocess(
    run_id: str,
    agent_id: str,
    agent_name: str,
    venv_python: str,
    entry_point: str,
    cwd: str,
    env: dict[str, str],
    log_path: Path,
    timeout: int,
) -> None:
    """Spawn the subprocess and stream its output."""
    db = get_database()
    agent_repo = AgentRepository(db)
    run_repo = RunRepository(db)

    start = time.time()

    try:
        proc = await asyncio.create_subprocess_exec(
            venv_python, entry_point,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
            env=env,
        )

        _active_runs[run_id] = {
            "pid": proc.pid,
            "process": proc,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "start": start,
        }

        with open(log_path, "w") as log_file:
            try:
                # Stream output line by line with a timeout wrapper
                async def _stream():
                    assert proc.stdout is not None
                    async for raw_line in proc.stdout:
                        line = raw_line.decode(errors="replace").rstrip("\n")
                        log_file.write(line + "\n")
                        log_file.flush()
                        await ws_manager.broadcast_log(run_id, line)

                await asyncio.wait_for(_stream(), timeout=timeout)
                await proc.wait()

            except asyncio.TimeoutError:
                logger.warning("Agent %s run %s timed out after %ds", agent_id, run_id, timeout)
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()

                duration = time.time() - start
                await run_repo.update_status(
                    run_id, "timeout",
                    exit_code=-1,
                    error_message=f"Execution timed out after {timeout}s",
                    duration_seconds=duration,
                )
                failures = await agent_repo.update_consecutive_failures(agent_id)
                if failures >= settings.FAILURE_ALERT_THRESHOLD:
                    await agent_repo.set_status(agent_id, "error")
                else:
                    await agent_repo.set_status(agent_id, "idle")
                return

        duration = time.time() - start
        exit_code = proc.returncode or 0

        if exit_code == 0:
            status = "success"
            await agent_repo.update_consecutive_failures(agent_id, reset=True)
        else:
            status = "failed"
            failures = await agent_repo.update_consecutive_failures(agent_id)
            if failures >= settings.FAILURE_ALERT_THRESHOLD:
                await agent_repo.set_status(agent_id, "error")

        await run_repo.update_status(
            run_id, status, exit_code=exit_code, duration_seconds=duration,
        )
        await agent_repo.increment_run_count(agent_id)
        if agent.get("status") != "error" if (agent := await agent_repo.get_by_id(agent_id)) else True:
            await agent_repo.set_status(agent_id, "idle")

    except Exception as exc:
        duration = time.time() - start
        logger.exception("Agent %s run %s crashed: %s", agent_id, run_id, exc)
        await run_repo.update_status(
            run_id, "failed", exit_code=-1,
            error_message=str(exc)[:2000], duration_seconds=duration,
        )
        failures = await agent_repo.update_consecutive_failures(agent_id)
        if failures >= settings.FAILURE_ALERT_THRESHOLD:
            await agent_repo.set_status(agent_id, "error")
        else:
            await agent_repo.set_status(agent_id, "idle")

    finally:
        _active_runs.pop(run_id, None)


async def stop_run(run_id: str) -> bool:
    """Send SIGTERM to a running agent subprocess."""
    info = _active_runs.get(run_id)
    if not info:
        return False

    proc = info["process"]
    agent_id = info["agent_id"]
    start = info["start"]

    try:
        os.kill(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    duration = time.time() - start
    db = get_database()
    run_repo = RunRepository(db)
    agent_repo = AgentRepository(db)
    await run_repo.update_status(run_id, "stopped", exit_code=-15, duration_seconds=duration)
    await agent_repo.set_status(agent_id, "idle")
    _active_runs.pop(run_id, None)

    logger.info("Run %s stopped", run_id)
    return True
