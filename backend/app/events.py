"""Bus de eventos en proceso para empujar novedades al dashboard por WebSocket."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind(self) -> None:
        """Guarda el bucle de eventos activo (se llama en el arranque)."""
        self._loop = asyncio.get_running_loop()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publica un evento. Seguro desde hilos (endpoints sincronos)."""
        if self._loop is None or self._loop.is_closed():
            return

        payload = {"type": event_type, "data": data}

        def _dispatch() -> None:
            for queue in list(self._subscribers):
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    try:
                        queue.get_nowait()
                        queue.put_nowait(payload)
                    except (asyncio.QueueEmpty, asyncio.QueueFull):
                        logger.debug("Se descarto un evento para un suscriptor lento")

        try:
            self._loop.call_soon_threadsafe(_dispatch)
        except RuntimeError:  # pragma: no cover - bucle cerrado durante el apagado
            pass


bus = EventBus()
