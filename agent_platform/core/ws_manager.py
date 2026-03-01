"""WebSocket connection manager.

Manages per-channel (run_id, global monitor) client sets and provides
broadcast helpers for log lines, resource metrics, and status changes.
"""

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        # channel -> set of connected websockets
        self._channels: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, channel: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._channels[channel].add(ws)
        logger.debug("WS client connected to channel %s", channel)

    async def disconnect(self, channel: str, ws: WebSocket) -> None:
        async with self._lock:
            self._channels[channel].discard(ws)
            if not self._channels[channel]:
                del self._channels[channel]

    async def broadcast(self, channel: str, data: dict[str, Any]) -> None:
        async with self._lock:
            clients = list(self._channels.get(channel, []))
        message = json.dumps(data)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._channels[channel].discard(ws)

    async def broadcast_log(self, run_id: str, line: str) -> None:
        await self.broadcast(f"logs:{run_id}", {"type": "log", "line": line})

    async def broadcast_metrics(
        self, run_id: str, cpu: float, memory_mb: float, elapsed: float
    ) -> None:
        await self.broadcast(
            f"metrics:{run_id}",
            {
                "type": "metrics",
                "cpu_percent": cpu,
                "memory_mb": memory_mb,
                "elapsed_seconds": elapsed,
            },
        )

    async def broadcast_monitor(self, data: dict[str, Any]) -> None:
        await self.broadcast("monitor:global", data)

    def has_subscribers(self, channel: str) -> bool:
        return bool(self._channels.get(channel))


ws_manager = WebSocketManager()
