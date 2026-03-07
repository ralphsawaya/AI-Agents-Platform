"""Per-agent virtual environment creation and management.

Each uploaded agent gets its own venv built from its requirements.txt.
Creation is fully async — the platform never blocks on pip installs.
"""

import asyncio
import logging
import sys
from pathlib import Path

from agent_platform.db.client import get_database
from agent_platform.db.repositories.agent_repo import AgentRepository

logger = logging.getLogger(__name__)


async def create_venv(agent_id: str, agent_path: str) -> None:
    """Create a virtual environment and install the agent's dependencies.

    Runs as async subprocesses so the event loop is never blocked.
    Updates the agent document's venv_ready flag on success or sets
    status to 'error' on failure.
    """
    agent_repo = AgentRepository(get_database())
    base = Path(agent_path)
    venv_dir = base / ".venv"

    # Locate the root folder inside the extraction directory
    root_dirs = [d for d in base.iterdir() if d.is_dir() and not d.name.startswith(".")]
    root_dir = root_dirs[0] if root_dirs else base

    requirements = root_dir / "requirements.txt"

    try:
        logger.info("Creating venv for agent %s at %s", agent_id, venv_dir)

        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "venv", "--clear", str(venv_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"venv creation failed (rc={proc.returncode}): {stderr.decode()}"
            )

        pip_path = venv_dir / "bin" / "pip"
        if not pip_path.exists():
            # Windows fallback
            pip_path = venv_dir / "Scripts" / "pip.exe"

        if requirements.exists():
            logger.info("Installing dependencies for agent %s", agent_id)
            proc = await asyncio.create_subprocess_exec(
                str(pip_path), "install", "-r", str(requirements),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(
                    f"pip install failed (rc={proc.returncode}): {stderr.decode()[-2000:]}"
                )

        await agent_repo.update(agent_id, {"venv_ready": True, "status": "idle"})
        logger.info("Venv ready for agent %s", agent_id)

    except Exception as exc:
        logger.error("Venv creation failed for agent %s: %s", agent_id, exc)
        await agent_repo.update(
            agent_id,
            {"venv_ready": False, "status": "error"},
        )
