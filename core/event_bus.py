"""
VORNEX Event Bus — bounded internal event transport.

One producer must never be able to stall the assistant.
Events are best-effort and bounded; critical control flow stays outside the bus.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Event:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class EventBus:
    def __init__(self, maxsize: int = 128):
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self._dropped = 0

    @property
    def dropped(self) -> int:
        return self._dropped

    def emit(self, kind: str, **data: Any) -> bool:
        event = Event(kind=kind, data=data)

        try:
            self._queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            self._dropped += 1
            return False

    async def get(self) -> Event:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    def qsize(self) -> int:
        return self._queue.qsize()
