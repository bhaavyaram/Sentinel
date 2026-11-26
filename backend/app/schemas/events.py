from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.base import ContractModel
from app.schemas.enums import Actor, EventType


class SentinelEvent(ContractModel):
    event_id: UUID
    ts: datetime
    application_id: UUID
    incident_id: UUID | None = None
    actor: Actor
    type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    policy_version: int | None = None