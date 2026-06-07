"""In-process async event bus, bridged to HMI clients over WebSocket.

Engine components publish typed events (scan, capture, roi_result, result,
storage_alarm, teaching_progress, ...). The API layer subscribes per WebSocket
connection and forwards JSON frames to the browser.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set


@dataclass
class Event:
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_json(self) -> Dict[str, Any]:
        return {"type": self.type, "ts": self.ts, "payload": self.payload}


class EventBus:
    """Fan-out pub/sub. Each subscriber gets its own bounded asyncio.Queue."""

    def __init__(self, max_queue: int = 256) -> None:
        self._subscribers: Set[asyncio.Queue] = set()
        self._max_queue = max_queue
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue)
        async with self._lock:
            self._subscribers.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._lock:
            self._subscribers.discard(q)

    async def publish(self, event_type: str, payload: Dict[str, Any] | None = None) -> None:
        event = Event(type=event_type, payload=payload or {})
        async with self._lock:
            targets: List[asyncio.Queue] = list(self._subscribers)
        for q in targets:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop the oldest frame to keep the live stream current.
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass

    def publish_threadsafe(self, loop: asyncio.AbstractEventLoop, event_type: str,
                           payload: Dict[str, Any] | None = None) -> None:
        """Publish from a non-async thread (e.g. an evdev reader thread)."""
        asyncio.run_coroutine_threadsafe(self.publish(event_type, payload), loop)
