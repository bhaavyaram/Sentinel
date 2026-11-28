"""The one way agents publish events that belong to an incident.

While incidents are fake (Backend Step 9 not shipped), the incident_events table cannot hold
an incident id (foreign key), so the id travels in the payload and the column stays null.
With REAL_INCIDENTS=true the id goes into the column, as Contracts section 7 intends.
"""

from uuid import UUID

from app.agents.settings import agent_settings
from app.events import publish
from app.schemas import SentinelEvent
from app.schemas.enums import Actor, EventType


def emit(
    application_id: UUID,
    incident_id: UUID,
    type: EventType,  # noqa: A002 - mirrors events.publish
    actor: Actor,
    payload: dict,
    policy_version: int | None = None,
) -> SentinelEvent:
    if agent_settings.real_incidents:
        return publish(
            application_id, type, actor, payload, incident_id=incident_id, policy_version=policy_version
        )
    return publish(
        application_id,
        type,
        actor,
        {**payload, "incident_id": str(incident_id)},
        incident_id=None,
        policy_version=policy_version,
    )