import uuid

import pytest
from pydantic import ValidationError

from app.schemas import (
    ActionProposal,
    ActionProposalDraft,
    AgentRole,
    ImpactReportDraft,
    RootCauseReportDraft,
)

DRAFT = {
    "action": "restart",
    "target_service": "cartservice",
    "parameters": {},
    "rationale": "Container exited; restart should recover it.",
    "evidence_refs": [],
}


def test_draft_finalize_fills_ids():
    incident_id = uuid.uuid4()
    proposal = ActionProposalDraft.model_validate(DRAFT).finalize(incident_id, AgentRole.recovery)
    assert isinstance(proposal, ActionProposal)
    assert proposal.incident_id == incident_id
    assert proposal.agent == AgentRole.recovery
    assert isinstance(proposal.proposal_id, uuid.UUID)


def test_drafts_reject_ids_from_the_model():
    with pytest.raises(ValidationError):
        ActionProposalDraft.model_validate({**DRAFT, "proposal_id": str(uuid.uuid4())})
    with pytest.raises(ValidationError):
        RootCauseReportDraft.model_validate({"incident_id": str(uuid.uuid4()), "hypotheses": []})
    with pytest.raises(ValidationError):
        ImpactReportDraft.model_validate(
            {
                "incident_id": str(uuid.uuid4()),
                "affected_services": [],
                "candidate_actions": [],
                "summary": "",
            }
        )


def test_report_drafts_finalize():
    incident_id = uuid.uuid4()
    root = RootCauseReportDraft.model_validate(
        {"hypotheses": [{"service": "redis-cart", "cause": "connection reset", "confidence": 0.8}]}
    ).finalize(incident_id)
    assert root.incident_id == incident_id
    impact = ImpactReportDraft.model_validate(
        {
            "affected_services": ["cartservice"],
            "candidate_actions": [
                {"action": "restart", "target_service": "cartservice", "blast_radius": ["frontend"]}
            ],
            "summary": "Cart is down.",
        }
    ).finalize(incident_id)
    assert impact.incident_id == incident_id