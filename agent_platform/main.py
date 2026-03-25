import asyncio
import logging
import logging.handlers
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agent_platform.config import settings
from agent_platform.db.client import close_db, connect_db, get_database
from agent_platform.db.indexes import ensure_indexes
from agent_platform.core.venv_manager import create_venv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            "agent_platform.log", maxBytes=10_000_000, backupCount=5
        ),
    ],
)

logger = logging.getLogger("agent_platform")

UI_DIR = Path(__file__).resolve().parent / "ui"
templates = Jinja2Templates(directory=str(UI_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Agent Platform …")
    await connect_db()
    db = get_database()
    await ensure_indexes(db)

    from agent_platform.db.repositories.strategy_repo import seed_builtin_strategies
    await seed_builtin_strategies()

    Path(settings.AGENTS_STORE_PATH).mkdir(parents=True, exist_ok=True)

    from agent_platform.core.scheduler import scheduler_service
    from agent_platform.core.monitor import monitor_service

    await scheduler_service.start(db)
    await monitor_service.start()

    # Load persisted trading config from MongoDB
    trading_cfg = await db["trading_config"].find_one({"_id": "default"})
    if trading_cfg and "trading_enabled" in trading_cfg:
        settings.trading_enabled = trading_cfg["trading_enabled"]
        logger.info("Loaded trading_enabled=%s from MongoDB", settings.trading_enabled)

    # Recover any builds that were interrupted (e.g. by a server restart)
    from agent_platform.db.repositories.agent_repo import AgentRepository
    agent_repo = AgentRepository(db)
    stuck = await db["agents"].find(
        {"venv_ready": False, "status": {"$ne": "error"}}
    ).to_list(length=100)
    for agent in stuck:
        logger.info("Recovering interrupted venv build for agent %s", agent["_id"])
        asyncio.create_task(create_venv(agent["_id"], agent["upload_path"]))

    logger.info("Platform ready.")
    yield

    await monitor_service.stop()
    await scheduler_service.shutdown()
    await close_db()
    logger.info("Platform shut down.")


app = FastAPI(title="AI Agent Platform", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(UI_DIR / "static")), name="static")

from agent_platform.api.routes.agents import router as agents_router  # noqa: E402
from agent_platform.api.routes.execution import router as execution_router  # noqa: E402
from agent_platform.api.routes.graph import router as graph_router  # noqa: E402
from agent_platform.api.routes.monitor import router as monitor_router  # noqa: E402
from agent_platform.api.routes.scheduler import router as scheduler_router  # noqa: E402
from agent_platform.api.routes.pages import router as pages_router  # noqa: E402
from agent_platform.api.routes.webhook import router as webhook_router  # noqa: E402
from agent_platform.api.routes.trading import router as trading_router  # noqa: E402
from agent_platform.api.routes.backtest import router as backtest_router  # noqa: E402
from agent_platform.api.routes.team_settings import router as team_settings_router  # noqa: E402
from agent_platform.api.routes.strategygpt import router as strategygpt_router  # noqa: E402

app.include_router(agents_router)
app.include_router(execution_router)
app.include_router(graph_router)
app.include_router(monitor_router)
app.include_router(scheduler_router)
app.include_router(pages_router)
app.include_router(webhook_router)
app.include_router(trading_router)
app.include_router(backtest_router)
app.include_router(team_settings_router)
app.include_router(strategygpt_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "agent_platform.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True,
        reload_excludes=[settings.AGENTS_STORE_PATH],
    )
