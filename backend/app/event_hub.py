"""In-memory fan-out of stored events to connected WebSocket clients.

Events are stored in PostgreSQL first (app/events.py). The hub only pushes them to
live subscribers. It never raises into the caller (Contracts section 7.1).
"""

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from uuid import UUID

from app.schemas import SentinelEvent

log = logging.getLogger(__name__)


@dataclass(eq=False)
class Subscriber:
    application_id: UUID
    loop: asyncio.AbstractEventLoop
    # Each item is (seq, SentinelEvent). seq is the server-side ordering number.
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)


class EventHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[UUID, set[Subscriber]] = {}

    def subscribe(self, application_id: UUID) -> Subscriber:
        """Must be called from inside the event loop that will read the queue."""
        sub = Subscriber(application_id=application_id, loop=asyncio.get_running_loop())
        with self._lock:
            self._subscribers.setdefault(application_id, set()).add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        with self._lock:
            subs = self._subscribers.get(sub.application_id)
            if subs is not None:
                subs.discard(sub)
                if not subs:
                    del self._subscribers[sub.application_id]

    def push(self, application_id: UUID, seq: int, event: SentinelEvent) -> None:
        """Safe to call from any thread. A failed push never raises."""
        with self._lock:
            targets = list(self._subscribers.get(application_id, ()))
        for sub in targets:
            try:
                sub.loop.call_soon_threadsafe(sub.queue.put_nowait, (seq, event))
            except Exception:  # e.g. the client's event loop is already closed
                log.warning("dropping a WebSocket subscriber after a failed push", exc_info=True)
                self.unsubscribe(sub)


hub = EventHub()