"""In-process publish/subscribe for live execution updates.

The execution worker publishes; the SSE endpoint subscribes. This keeps the real-time UI
honest — every event corresponds to a step that actually happened.

Redis becomes the transport when more than one process serves the API; the interface does
not change.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.schemas.execution import ExecutionEvent


class ExecutionBus:
    def __init__(self, history_size: int = 500) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[ExecutionEvent]]] = defaultdict(set)
        self._history: dict[str, list[ExecutionEvent]] = defaultdict(list)
        self._history_size = history_size
        self._lock = asyncio.Lock()

    async def publish(self, event: ExecutionEvent) -> None:
        history = self._history[event.execution_id]
        history.append(event)
        if len(history) > self._history_size:
            del history[: len(history) - self._history_size]
        for queue in list(self._subscribers[event.execution_id]):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover - slow consumer
                pass

    def history(self, execution_id: str) -> list[ExecutionEvent]:
        return list(self._history.get(execution_id, ()))

    @asynccontextmanager
    async def subscribe(self, execution_id: str) -> AsyncIterator[asyncio.Queue[ExecutionEvent]]:
        queue: asyncio.Queue[ExecutionEvent] = asyncio.Queue(maxsize=256)
        async with self._lock:
            self._subscribers[execution_id].add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                self._subscribers[execution_id].discard(queue)
                if not self._subscribers[execution_id]:
                    self._subscribers.pop(execution_id, None)

    def clear(self, execution_id: str) -> None:
        self._history.pop(execution_id, None)


bus = ExecutionBus()
