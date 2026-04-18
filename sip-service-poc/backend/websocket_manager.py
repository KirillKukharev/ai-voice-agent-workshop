from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks WebSocket connections and performs fan-out delivery."""

    GLOBAL_KEY = "__global__"
    PING_INTERVAL = 30
    PONG_TIMEOUT = 60

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._last_pong: dict[WebSocket, float] = {}
        self._heartbeat_task: asyncio.Task | None = None

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        key = session_id or self.GLOBAL_KEY
        async with self._lock:
            self._connections[key].add(websocket)
            self._last_pong[websocket] = time.time()
        logger.debug("WebSocket connected. session_id=%s", session_id)

        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            for key, sockets in list(self._connections.items()):
                if websocket in sockets:
                    sockets.remove(websocket)
                    if not sockets:
                        self._connections.pop(key, None)
                    break
            self._last_pong.pop(websocket, None)
        logger.debug("WebSocket disconnected")

    async def broadcast(self, message: dict, session_id: str = None) -> None:
        targets = await self._gather_targets(session_id)
        if not targets:
            logger.debug(
                "No active WebSocket connections for session=%s payload_keys=%s",
                session_id,
                list(message.keys()),
            )
            return

        disconnected: set[WebSocket] = set()
        for websocket in targets:
            try:
                await websocket.send_json(message)
            except (WebSocketDisconnect, RuntimeError, ConnectionError) as error:
                logger.warning("Failed to push message to WebSocket (connection closed): %s", error)
                disconnected.add(websocket)
            except Exception as error:
                logger.error(
                    "Unexpected error while sending WebSocket message: %s",
                    error,
                    exc_info=True,
                )
                disconnected.add(websocket)

        for websocket in disconnected:
            await self.disconnect(websocket)

    async def _gather_targets(self, session_id: str) -> set[WebSocket]:
        async with self._lock:
            targets: set[WebSocket] = set(self._connections.get(self.GLOBAL_KEY, set()))
            if session_id and session_id in self._connections:
                targets = targets.union(self._connections[session_id])
        return targets

    def mark_pong_received(self, websocket: WebSocket) -> None:
        """Marks the receipt of pong from the client."""
        self._last_pong[websocket] = time.time()

    async def _heartbeat_loop(self) -> None:
        """Background task for sending ping and checking pong."""
        logger.info("Heartbeat loop started")
        try:
            while True:
                await asyncio.sleep(self.PING_INTERVAL)

                async with self._lock:
                    all_connections: set[WebSocket] = set()
                    for sockets in self._connections.values():
                        all_connections.update(sockets)

                if not all_connections:
                    continue

                current_time = time.time()
                dead_connections: set[WebSocket] = set()

                for websocket in all_connections:
                    last_pong_time = self._last_pong.get(websocket, current_time)
                    time_since_pong = current_time - last_pong_time

                    if time_since_pong > self.PONG_TIMEOUT:
                        logger.warning(
                            "WebSocket connection timeout (no pong for %.1fs), closing",
                            time_since_pong,
                        )
                        dead_connections.add(websocket)
                    else:
                        try:
                            await websocket.send_json({"type": "ping"})
                        except (WebSocketDisconnect, RuntimeError, ConnectionError):
                            dead_connections.add(websocket)
                        except Exception as error:
                            logger.error("Error sending ping: %s", error, exc_info=True)
                            dead_connections.add(websocket)

                for websocket in dead_connections:
                    try:
                        await websocket.close()
                    except Exception as e:
                        logger.error("Error sending ping: %s", e, exc_info=True)
                        pass
                    await self.disconnect(websocket)

        except asyncio.CancelledError:
            logger.info("Heartbeat loop cancelled")
            raise
        except Exception as error:
            logger.error("Heartbeat loop error: %s", error, exc_info=True)
