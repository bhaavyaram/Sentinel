"""Placeholder guardrail gateway (Backend Step 6).

Only enforces what exists today: chaos tools need a human, and anything else is
denied by default. Step 8 replaces this with the real policy engine behind the
same function, gateway.submit(request) -> GatewayDecision.
"""

import json

from sqlalchemy import text

from app.db import SessionLocal
from app.schemas import (
    CHAOS_TOOLS,
    BlastRadius,
    GatewayDecision,
    GatewayRequest,
    ReasonCode,
    Verdict,
)

PLACEHOLDER_POLICY_VERSION = 1  # no policy store yet; Step 8 supplies real versions


def _write_audit(request: GatewayRequest, decision: GatewayDecision) -> None:
    """Contracts invariant 7: the audit record is written before any tool executes."""
    with SessionLocal() as db:
        db.execute(
            text(
                "insert into audit_log (id, actor, tool, parameters, verdict, reason_code, "
                "reason, policy_version, dry_run) "
                "values (gen_random_uuid(), :actor, :tool, cast(:parameters as jsonb), :verdict, "
                ":reason_code, :reason, :policy_version, :dry_run)"
            ),
            {
                "actor": request.caller.value,
                "tool": request.tool,
                "parameters": json.dumps(
                    {"target_service": request.target_service, **request.parameters}
                ),
                "verdict": decision.verdict.value,
                "reason_code": decision.reason_code.value,
                "reason": decision.reason,
                "policy_version": decision.policy_version,
                "dry_run": request.dry_run,
            },
        )
        db.commit()


def submit(request: GatewayRequest) -> GatewayDecision:
    if request.tool in CHAOS_TOOLS and not request.initiated_by_human:
        verdict = Verdict.block
        code = ReasonCode.chaos_requires_human
        reason = "Fault injection must be started by a person from the dashboard, not by an agent."
    elif request.tool in CHAOS_TOOLS:
        verdict = Verdict.allow
        code = ReasonCode.allowed
        reason = "Placeholder gateway: human-initiated chaos is allowed."
    else:
        verdict = Verdict.block
        code = ReasonCode.no_rule
        reason = "No rule allows this tool yet (deny by default)."

    decision = GatewayDecision(
        request_id=request.request_id,
        verdict=verdict,
        reason_code=code,
        reason=reason,
        blast_radius=BlastRadius(affected_services=[request.target_service], dependents_count=0),
        risk_score=0,
        matched_rules=[],
        policy_version=PLACEHOLDER_POLICY_VERSION,
        approval_id=None,
    )
    _write_audit(request, decision)  # if this raises, nothing executes
    return decision