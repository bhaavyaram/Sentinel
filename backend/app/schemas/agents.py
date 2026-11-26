from uuid import UUID

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr

from app.schemas.base import ContractModel
from app.schemas.enums import ActionType, AgentRole

# Contracts: parameters are Record<string, string | number | boolean>.
ParamValue = StrictBool | StrictInt | StrictFloat | StrictStr


class ActionProposal(ContractModel):
    proposal_id: UUID
    incident_id: UUID
    agent: AgentRole
    action: ActionType
    target_service: str
    parameters: dict[str, ParamValue] = Field(default_factory=dict)
    rationale: str  # display only; the gateway never evaluates it
    evidence_refs: list[UUID] = Field(default_factory=list)  # incident_event ids


class Hypothesis(ContractModel):
    service: str
    cause: str
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[UUID] = Field(default_factory=list)


class RootCauseReport(ContractModel):
    incident_id: UUID
    hypotheses: list[Hypothesis]


class CandidateAction(ContractModel):
    action: ActionType
    target_service: str
    blast_radius: list[str]


class ImpactReport(ContractModel):
    incident_id: UUID
    affected_services: list[str]
    candidate_actions: list[CandidateAction]
    summary: str