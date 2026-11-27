"""Latest known health per service, shared by the monitor and the map endpoint."""

import threading
from uuid import UUID

from app.schemas import ServiceHealth

DEGRADED_AFTER = 2  # consecutive degraded observations before we report degraded


class HealthTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current: dict[tuple[UUID, str], ServiceHealth] = {}
        self._degraded_streak: dict[tuple[UUID, str], int] = {}

    def get(self, application_id: UUID, service: str) -> ServiceHealth:
        with self._lock:
            return self._current.get((application_id, service), ServiceHealth.unknown)

    def observe(
        self, application_id: UUID, service: str, raw: ServiceHealth
    ) -> tuple[ServiceHealth, ServiceHealth] | None:
        """Records one observation. Returns (from, to) when the reported health changed."""
        key = (application_id, service)
        with self._lock:
            previous = self._current.get(key)
            if raw == ServiceHealth.degraded:
                self._degraded_streak[key] = self._degraded_streak.get(key, 0) + 1
            else:
                self._degraded_streak[key] = 0

            if previous is None:  # first time we see this service
                self._current[key] = raw
                if raw in (ServiceHealth.healthy, ServiceHealth.unknown):
                    return None  # starting out healthy is not news
                return (ServiceHealth.unknown, raw)

            if raw == ServiceHealth.degraded and self._degraded_streak[key] < DEGRADED_AFTER:
                return None  # one bad probe is not enough yet
            if raw == previous:
                return None

            self._current[key] = raw
            return (previous, raw)


tracker = HealthTracker()