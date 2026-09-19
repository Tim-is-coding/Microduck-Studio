"""Plain-language event log (§6.4): every state change carries `text.de` for the Studio
and structured `data` for debugging."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Literal

from pydantic import Field

from .common import Strict, Text

Level = Literal["info", "warn", "error"]


class Event(Strict):
    ts: float
    level: Level = "info"
    kind: str
    text: Text
    data: dict[str, Any] = Field(default_factory=dict)


class EventBus:
    """In-process fan-out. Subscribers get their own queue; slow ones drop, never block."""

    def __init__(self, history: int = 200, queue_size: int = 500) -> None:
        self.history: deque[Event] = deque(maxlen=history)
        self._queues: list[asyncio.Queue[Event]] = []
        self._queue_size = queue_size

    def publish(self, event: Event) -> None:
        self.history.append(event)
        for q in list(self._queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def emit(
        self, kind: str, de: str, *, level: Level = "info", en: str | None = None, **data: Any
    ) -> Event:
        event = Event(ts=time.time(), level=level, kind=kind, text=Text(de=de, en=en), data=data)
        self.publish(event)
        return event

    def subscribe(self) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._queue_size)
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        if q in self._queues:
            self._queues.remove(q)
