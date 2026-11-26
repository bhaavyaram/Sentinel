import uuid

import pytest

from app.chaos.runner import TOOL_FOR_FAULT, _clean_parameters
from app.errors import AppError
from app.gateway import placeholder
from app.schemas import (
    CHAOS_TOOLS,
    ActionType,
    Actor,
    FaultType,
    GatewayRequest,
    ReasonCode,
    Verdict,
)


@pytest.fixture(autouse=True)
def no_audit_db(monkeypatch):
    monkeypatch.setattr(placeholder, "_write_audit", lambda request, decision: None)


def make_request(tool: str, caller: Actor, human: bool) -> GatewayRequest:
    return GatewayRequest(
        request_id=uuid.uuid4(),
        incident_id=None,
        caller=caller,
        tool=tool,
        action=ActionType.inject_fault,
        target_service="cartservice",
        parameters={},
        initiated_by_human=human,
        dry_run=False,
    )


def test_chaos_from_agent_is_blocked():
    decision = placeholder.submit(make_request("inject_crash", Actor.recovery, human=False))
    assert decision.verdict == Verdict.block
    assert decision.reason_code == ReasonCode.chaos_requires_human


def test_chaos_from_human_is_allowed():
    decision = placeholder.submit(make_request("inject_crash", Actor.human, human=True))
    assert decision.verdict == Verdict.allow


def test_unknown_tool_is_denied_by_default():
    decision = placeholder.submit(make_request("restart_service", Actor.recovery, human=False))
    assert decision.verdict == Verdict.block
    assert decision.reason_code == ReasonCode.no_rule


def test_every_fault_maps_to_a_chaos_tool():
    assert set(TOOL_FOR_FAULT) == set(FaultType)
    assert set(TOOL_FOR_FAULT.values()) <= CHAOS_TOOLS


def test_latency_defaults_and_validation():
    assert _clean_parameters(FaultType.latency, {}) == {"latency_ms": 1000}
    with pytest.raises(AppError):
        _clean_parameters(FaultType.latency, {"latency_ms": -5})