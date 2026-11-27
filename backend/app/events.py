"""publish(): the one function all backend code uses to emit events (Contracts 7.1)."""

import json
import logging
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.event_hub import hub
from app.repository import events as events_repo
from app.schemas import Actor, EventType, SentinelEvent

log = logging.getLogger(__name__)


class EventPublishError(Exception):
    """The event could not be validated or stored. Nothing was sent to any client."""


# Payload keys required per event type (Contracts section 7).
# proposal_created and gateway_decision carry a whole ActionProposal / GatewayDecision;
# we require only their identifying keys here.
_EXPERIMENT = {"experiment_id", "service", "fault_type"}
REQUIRED_KEYS: dict[EventType, set[str]] = {
    EventType.experiment_started: _EXPERIMENT,
    EventType.experiment_ended: _EXPERIMENT,
    EventType.service_health_changed: {"service", "from", "to"},
    EventType.incident_opened: {"severity", "trigger_service"},
    EventType.incident_status_changed: {"from", "to"},
    EventType.agent_step: {"agent", "summary", "detail_ref"},
    EventType.proposal_created: {"proposal_id", "action", "target_service"},
    EventType.gateway_decision: {"request_id", "verdict", "reason_code"},
    EventType.approval_requested: {"approval_id", "proposal_id"},
    EventType.approval_decided: {"approval_id", "proposal_id", "decision", "decided_by"},
    EventType.action_executed: {"tool", "result_ok", "detail"},
    EventType.validation_completed: {"result", "metrics_before", "metrics_after"},
    EventType.postmortem_ready: {"postmortem_id"},
    EventType.policy_changed: {"from_version", "to_version", "changed_by"},
}


def publish(
    application_id: UUID,
    type: EventType,  # noqa: A002 - the name comes from the contract
    actor: Actor,
    payload: dict,
    incident_id: UUID | None = None,
    policy_version: int | None = None,
) -> SentinelEvent:
    event_type = EventType(type)
    actor = Actor(actor)

    missing = REQUIRED_KEYS[event_type] - payload.keys()
    if missing:
        raise EventPublishError(f"{event_type.value} payload is missing keys: {sorted(missing)}")

    try:
        # Round-trip through JSON so UUIDs, datetimes and enums become plain JSON values.
        safe_payload = json.loads(json.dumps(payload, default=str))
        seq, event = events_repo.insert_event(
            application_id, incident_id, actor.value, event_type.value, safe_payload, policy_version
        )
    except (SQLAlchemyError, TypeError, ValueError) as exc:
        raise EventPublishError(f"could not store {event_type.value} event: {exc}") from exc

    hub.push(application_id, seq, event)  # never raises
    return event