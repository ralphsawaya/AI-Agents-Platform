"""Server-rendered page routes (Jinja2 templates)."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

UI_DIR = Path(__file__).resolve().parent.parent.parent / "ui"
templates = Jinja2Templates(directory=str(UI_DIR / "templates"))


def _static_url(path: str) -> str:
    """Return a versioned static URL so browsers never serve stale cache."""
    file_path = UI_DIR / "static" / path
    try:
        mtime = int(file_path.stat().st_mtime)
    except FileNotFoundError:
        mtime = 0
    return f"/static/{path}?v={mtime}"


templates.env.globals["static_url"] = _static_url

router = APIRouter(tags=["pages"])


@router.get("/", include_in_schema=False)
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/agents/{agent_id}", include_in_schema=False)
async def agent_detail_page(request: Request, agent_id: str):
    return templates.TemplateResponse(
        "agent_detail.html", {"request": request, "agent_id": agent_id}
    )


@router.get("/monitor", include_in_schema=False)
async def monitor_page(request: Request):
    return templates.TemplateResponse("monitor.html", {"request": request})


@router.get("/scheduler", include_in_schema=False)
async def scheduler_page(request: Request):
    return templates.TemplateResponse("scheduler.html", {"request": request})


@router.get("/graph", include_in_schema=False)
async def graph_page(request: Request):
    return templates.TemplateResponse("graph.html", {"request": request})
