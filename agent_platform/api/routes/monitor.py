"""Monitoring API routes and WebSocket endpoints for live logs/metrics."""

import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agent_platform.core.monitor import monitor_service
from agent_platform.core.ws_manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["monitor"])


def _ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


@router.get("/api/monitor/running")
async def get_running():
    snapshot = await monitor_service.get_running_snapshot()
    return _ok(snapshot)


@router.get("/api/monitor/alerts")
async def get_alerts():
    alerts = await monitor_service.get_alerts()
    return _ok(alerts)


@router.websocket("/ws/logs/{run_id}")
async def ws_logs(websocket: WebSocket, run_id: str):
    """Stream log lines for a specific run in real-time."""
    channel = f"logs:{run_id}"
    await ws_manager.connect(channel, websocket)
    try:
        while True:
            # Keep connection alive; client doesn't need to send data
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(channel, websocket)


@router.websocket("/ws/metrics/{run_id}")
async def ws_metrics(websocket: WebSocket, run_id: str):
    """Stream CPU/memory metrics for a specific run in real-time."""
    channel = f"metrics:{run_id}"
    await ws_manager.connect(channel, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(channel, websocket)


@router.websocket("/ws/monitor")
async def ws_global_monitor(websocket: WebSocket):
    """Global monitor feed — broadcasts all active run metrics."""
    channel = "monitor:global"
    await ws_manager.connect(channel, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(channel, websocket)
