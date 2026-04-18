from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass

from .schemas import DashboardEvent
from .websocket_manager import ConnectionManager

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EventBusConfig:
    """Configuration options for the in-memory event bus."""

    history_size: int = 1000
    replay_batch: int = 25


class EventBus:
    """Coordinates event routing between REST endpoints and WebSocket clients."""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        config: EventBusConfig | None = None,
    ) -> None:
        self._connection_manager = connection_manager
        self._config = config or EventBusConfig()
        self._history: deque[DashboardEvent] = deque(maxlen=self._config.history_size)
        self._lock = asyncio.Lock()

    async def publish(self, event: DashboardEvent) -> None:
        """Persist event to history and push to all interested WebSocket clients."""
        async with self._lock:
            self._history.append(event)
        await self._connection_manager.broadcast(event.model_dump(), session_id=event.session_id)
        logger.debug(
            "Event %s published for session=%s",
            event.event,
            event.session_id or "broadcast",
        )

    async def replay(self, session_id: str | None) -> list[DashboardEvent]:
        """Yield the most recent events relevant for a connecting client."""
        async with self._lock:
            if session_id is None:
                recent = list(self._history)[-self._config.replay_batch :]
            else:
                recent = [
                    event
                    for event in list(self._history)[-self._config.replay_batch :]
                    if event.session_id in (None, session_id)
                ]
        return recent
