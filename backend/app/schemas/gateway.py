from uuid import UUID

from pydantic import Field

from app.schemas.agents import ParamValue
from app.schemas.base import ContractModel
from app.schemas.enums import ActionType, Actor, ReasonCode, Verdict


class GatewayRequest(ContractModel):
    request_id: UUID
    incident_id: UUID | None = None  # null for dashboard-initiated chaos
    caller: Actor
    tool: str
    action: ActionType
    target_service: str
    parameters: dict[str, ParamValue] = Field(default_factory=dict)
    initiated_by_human: bool  # true only for calls from a dashboard user action
    dry_run: bool  # true for the policy test panel; never executes


class BlastRadius(ContractModel):
    affected_services: list[str]
    dependents_count: int = Field(ge=0)


class GatewayDecision(ContractModel):
    request_id: UUID
    verdict: Verdict
    reason_code: ReasonCode
    reason: str  # plain language, shown in the UI
    blast_radius: BlastRadius
    risk_score: int = Field(ge=0, le=100)
    matched_rules: list[str] = Field(default_factory=list)
    policy_version: int = Field(ge=1)
    approval_id: UUID | None = None  # set when verdict is needs_approval