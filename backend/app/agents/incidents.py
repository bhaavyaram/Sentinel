"""Incident lifecycle interface (Contracts 8.6) and a fake with the same signatures.

The real functions arrive in Backend Step 9 (app/repository/incidents.py). Like the real ones,
the fake publishes the incident events itself, so agents never publish incident_opened or
incident_status_changed by hand.
"""

from typing import Protocol
from uuid import UUID, uuid4

from app.agents.emit import emit
from app.schemas.enums import Actor, EventType, IncidentStatus, Severity


class IncidentApi(Protocol):
    def open_incident(self, application_id: UUID, severity: Severity, trigger_service: str) -> UUID: ...

    def set_status(self, incident_id: UUID, status: IncidentStatus) -> None: ...

    def close_incident(
        self, incident_id: UUID, status: IncidentStatus, root_cause_summary: str | None
    ) -> None: ...


class FakeIncidents:
    def __init__(self) -> None:
        self._application: dict[UUID, UUID] = {}
        self._status: dict[UUID, IncidentStatus] = {}
        self.root_cause: dict[UUID, str | None] = {}

    def open_incident(self, application_id: UUID, severity: Severity, trigger_service: str) -> UUID:
        incident_id = uuid4()
        self._application[incident_id] = application_id
        self._status[incident_id] = IncidentStatus.open
        emit(
            application_id,
            incident_id,
            EventType.incident_opened,
            Actor.monitor,
            {"severity": severity.value, "trigger_service": trigger_service},
        )
        return incident_id

    def set_status(self, incident_id: UUID, status: IncidentStatus) -> None:
        previous = self._status[incident_id]  # an unknown incident is a programming error
        if previous == status:
            return
        self._status[incident_id] = status
        emit(
            self._application[incident_id],
            incident_id,
            EventType.incident_status_changed,
            Actor.system,
            {"from": previous.value, "to": status.value},
        )

    def close_incident(
        self, incident_id: UUID, status: IncidentStatus, root_cause_summary: str | None
    ) -> None:
        if status not in (IncidentStatus.resolved, IncidentStatus.failed):
            raise ValueError("close_incident needs the status resolved or failed")
        self.root_cause[incident_id] = root_cause_summary
        self.set_status(incident_id, status)

    def status_of(self, incident_id: UUID) -> IncidentStatus:
        return self._status[incident_id]