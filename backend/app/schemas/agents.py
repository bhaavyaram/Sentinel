from uuid import UUID, uuid4

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


# --- Drafts (Contracts v0.2 section 3) ---------------------------------------
# The model returns a draft. The orchestrator adds the IDs, so an LLM never invents them.


class ActionProposalDraft(ContractModel):
    action: ActionType
    target_service: str
    parameters: dict[str, ParamValue] = Field(default_factory=dict)
    rationale: str
    evidence_refs: list[UUID] = Field(default_factory=list)

    def finalize(self, incident_id: UUID, agent: AgentRole) -> ActionProposal:
        return ActionProposal(
            proposal_id=uuid4(),
            incident_id=incident_id,
            agent=agent,
            **self.model_dump(),
        )


class RootCauseReportDraft(ContractModel):
    hypotheses: list[Hypothesis]

    def finalize(self, incident_id: UUID) -> RootCauseReport:
        return RootCauseReport(incident_id=incident_id, **self.model_dump())


class ImpactReportDraft(ContractModel):
    affected_services: list[str]
    candidate_actions: list[CandidateAction]
    summary: str

    def finalize(self, incident_id: UUID) -> ImpactReport:
        return ImpactReport(incident_id=incident_id, **self.model_dump())