"""Monitor agent (design D4): deterministic rules, no LLM.

Opens one incident per failing service, once. The service is forgotten when it reports healthy
again. 'unknown' (for example the first seconds after a backend restart) changes nothing.
"""

import logging
from collections.abc import Callable, Iterable
from uuid import UUID

from app.agents.catalog import ServiceInfo, list_application_ids, load_services
from app.agents.emit import emit
from app.agents.incidents import IncidentApi
from app.monitoring.state import tracker
from app.schemas.enums import Actor, EventType, ServiceHealth, Severity

log = logging.getLogger(__name__)

# on_incident(application_id, incident_id, trigger_service) starts the workflow (step 7)
OnIncident = Callable[[UUID, UUID, str], None]


def severity_for(health: ServiceHealth, critical: bool) -> Severity:
    if health == ServiceHealth.down:
        return Severity.critical if critical else Severity.high
    return Severity.high if critical else Severity.medium  # degraded


class Monitor:
    def __init__(
        self,
        incidents: IncidentApi,
        get_health: Callable[[UUID, str], ServiceHealth] = tracker.get,
        on_incident: OnIncident | None = None,
    ) -> None:
        self._incidents = incidents
        self._get_health = get_health
        self._on_incident = on_incident
        self._active: dict[tuple[UUID, str], UUID] = {}

    def check(self, application_id: UUID, services: Iterable[ServiceInfo]) -> list[UUID]:
        """Looks at every service once. Returns the ids of the incidents it opened."""
        opened: list[UUID] = []
        for service in services:
            health = self._get_health(application_id, service.name)
            key = (application_id, service.name)
            if health in (ServiceHealth.down, ServiceHealth.degraded):
                if key in self._active:
                    continue
                incident_id = self._incidents.open_incident(
                    application_id, severity_for(health, service.critical), service.name
                )
                self._active[key] = incident_id
                emit(
                    application_id,
                    incident_id,
                    EventType.agent_step,
                    Actor.monitor,
                    {
                        "agent": "monitor",
                        "summary": f"{service.name} is {health.value}; incident opened",
                        "detail_ref": f"health:{service.name}",
                        "health": health.value,
                    },
                )
                opened.append(incident_id)
                if self._on_incident is not None:
                    try:
                        self._on_incident(application_id, incident_id, service.name)
                    except Exception:  # one failing workflow must not stop the monitor
                        log.exception("workflow for incident %s failed", incident_id)
            elif health == ServiceHealth.healthy:
                self._active.pop(key, None)
        return opened

    def sweep_once(
        self,
        list_apps: Callable[[], list[UUID]] = list_application_ids,
        load: Callable[[UUID], dict[str, ServiceInfo]] = load_services,
    ) -> None:
        """One pass over every connected application. This is what the worker will call."""
        for application_id in list_apps():
            self.check(application_id, load(application_id).values())