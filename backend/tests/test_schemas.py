import uuid

import pytest
from pydantic import ValidationError

from app.schemas import (
    CHAOS_TOOLS,
    TOOL_ACTION_MAP,
    ActionProposal,
    ActionType,
    AdapterFile,
    GatewayDecision,
    Hypothesis,
    Policy,
    SentinelEvent,
)


def uid() -> str:
    return str(uuid.uuid4())


def proposal_data(**overrides) -> dict:
    data = {
        "proposal_id": uid(),
        "incident_id": uid(),
        "agent": "recovery",
        "action": "restart",
        "target_service": "cartservice",
        "parameters": {"replicas": 2, "force": False},
        "rationale": "Service is down; restart should recover it.",
        "evidence_refs": [uid()],
    }
    data.update(overrides)
    return data


def adapter_data() -> dict:
    return {
        "app": "online-boutique",
        "version": 1,
        "description": "Demo shop",
        "services": [
            {
                "name": "cartservice",
                "container": "cartservice",
                "type": "stateless",
                "critical": False,
                "health": "/healthz",
                "faults": ["crash", "latency"],
            },
            {
                "name": "redis-cart",
                "container": "redis-cart",
                "type": "stateful",
                "critical": True,
                "faults": ["connection_failure"],
            },
        ],
        "declared_dependencies": [{"from": "cartservice", "to": "redis-cart"}],
    }


def policy_data() -> dict:
    return {
        "version": 1,
        "name": "balanced",
        "preset": "balanced",
        "matrix": {"recovery": {"restart": "allow"}},
        "service_rules": [],
        "thresholds": {"max_affected_services": 3, "max_dependents": 3, "approval_risk_score": 60},
        "protected": {"services": [], "actions": [], "pairs": []},
        "approval": {"approver_role": "admin", "timeout_seconds": 300, "on_timeout": "deny"},
        "created_by": "admin",
        "created_at": "2026-11-26T10:00:00Z",
    }


def test_action_proposal_valid():
    p = ActionProposal.model_validate(proposal_data())
    assert p.action == ActionType.restart
    assert p.parameters["replicas"] == 2
    assert p.parameters["force"] is False


def test_action_proposal_rejects_non_agent_role():
    with pytest.raises(ValidationError):
        ActionProposal.model_validate(proposal_data(agent="human"))


def test_unknown_enum_value_is_rejected():
    with pytest.raises(ValidationError):
        ActionProposal.model_validate(proposal_data(action="format_disk"))


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        ActionProposal.model_validate(proposal_data(sneaky="extra"))


def test_confidence_must_be_between_0_and_1():
    with pytest.raises(ValidationError):
        Hypothesis.model_validate({"service": "a", "cause": "b", "confidence": 1.5})


def test_risk_score_must_be_between_0_and_100():
    with pytest.raises(ValidationError):
        GatewayDecision.model_validate(
            {
                "request_id": uid(),
                "verdict": "allow",
                "reason_code": "allowed",
                "reason": "ok",
                "blast_radius": {"affected_services": [], "dependents_count": 0},
                "risk_score": 101,
                "matched_rules": [],
                "policy_version": 1,
                "approval_id": None,
            }
        )


def test_adapter_valid():
    adapter = AdapterFile.model_validate(adapter_data())
    assert adapter.services[0].name == "cartservice"
    dumped = adapter.model_dump(by_alias=True)
    assert dumped["declared_dependencies"][0]["from"] == "cartservice"


def test_adapter_rejects_unknown_fault_type():
    data = adapter_data()
    data["services"][0]["faults"] = ["meteor_strike"]
    with pytest.raises(ValidationError):
        AdapterFile.model_validate(data)


def test_adapter_rejects_unknown_field():
    data = adapter_data()
    data["services"][0]["color"] = "blue"
    with pytest.raises(ValidationError):
        AdapterFile.model_validate(data)


def test_adapter_rejects_unknown_dependency_service():
    data = adapter_data()
    data["declared_dependencies"] = [{"from": "cartservice", "to": "ghost"}]
    with pytest.raises(ValidationError):
        AdapterFile.model_validate(data)


def test_policy_on_timeout_must_be_deny():
    data = policy_data()
    data["approval"]["on_timeout"] = "allow"
    with pytest.raises(ValidationError):
        Policy.model_validate(data)


def test_policy_matrix_rejects_human_role():
    data = policy_data()
    data["matrix"] = {"human": {"restart": "allow"}}
    with pytest.raises(ValidationError):
        Policy.model_validate(data)


def test_tool_action_mapping():
    assert len(TOOL_ACTION_MAP) == 9
    assert TOOL_ACTION_MAP["restart_service"] == ActionType.restart
    assert TOOL_ACTION_MAP["inject_latency"] == ActionType.inject_fault
    assert TOOL_ACTION_MAP["clear_fault"] == ActionType.clear_fault
    assert CHAOS_TOOLS == {
        "inject_crash",
        "inject_latency",
        "inject_timeout",
        "break_db_connection",
        "clear_fault",
    }


def test_event_rejects_unknown_type():
    with pytest.raises(ValidationError):
        SentinelEvent.model_validate(
            {
                "event_id": uid(),
                "ts": "2026-11-26T10:00:00Z",
                "application_id": uid(),
                "incident_id": None,
                "actor": "system",
                "type": "something_new",
                "payload": {},
                "policy_version": None,
            }
        )