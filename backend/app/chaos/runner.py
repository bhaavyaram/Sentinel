"""Starts and clears experiments: asks the gateway first, then applies the fault."""

import uuid

from sqlalchemy.orm import Session

from app import gateway
from app.chaos import docker_ctl, toxiproxy
from app.errors import AppError
from app.repository import experiments as repo
from app.schemas import Actor, ActionType, FaultType, GatewayRequest, Verdict
from app.schemas.experiments import ExperimentCreate, ExperimentRecord

TOOL_FOR_FAULT: dict[FaultType, str] = {
    FaultType.crash: "inject_crash",
    FaultType.latency: "inject_latency",
    FaultType.timeout: "inject_timeout",
    FaultType.connection_failure: "break_db_connection",
}


def _positive_int(params: dict, key: str, default: int | None = None) -> int | None:
    value = params.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AppError(422, "validation_error", f"{key} must be a positive integer")
    return value


def _clean_parameters(fault: FaultType, params: dict) -> dict:
    cleaned: dict = {}
    if fault == FaultType.latency:
        cleaned["latency_ms"] = _positive_int(params, "latency_ms", 1000)
    duration = _positive_int(params, "duration_s")
    if duration is not None:
        cleaned["duration_s"] = duration  # recorded only; automatic expiry is not built yet
    return cleaned


def _ask_gateway(tool: str, action: ActionType, service: str, parameters: dict) -> None:
    request = GatewayRequest(
        request_id=uuid.uuid4(),
        incident_id=None,
        caller=Actor.human,
        tool=tool,
        action=action,
        target_service=service,
        parameters=parameters,
        initiated_by_human=True,  # these routes are only called from the dashboard
        dry_run=False,
    )
    decision = gateway.submit(request)
    if decision.verdict != Verdict.allow:
        raise AppError(403, "action_blocked", decision.reason)


def _apply(fault: FaultType, experiment_id: uuid.UUID, svc: dict, project: str | None, params: dict) -> None:
    proxy, toxic = svc["name"], f"sentinel-{experiment_id}"
    if fault == FaultType.crash:
        docker_ctl.kill_container(svc["container"], project)
    elif fault == FaultType.latency:
        toxiproxy.add_toxic(proxy, toxic, "latency", {"latency": params["latency_ms"], "jitter": 0})
    elif fault == FaultType.timeout:
        toxiproxy.add_toxic(proxy, toxic, "timeout", {"timeout": 0})  # 0 = hold connection, send nothing
    else:  # connection_failure
        toxiproxy.set_enabled(proxy, False)


def _revert(fault: FaultType, experiment_id: uuid.UUID, svc: dict, project: str | None) -> None:
    proxy, toxic = svc["name"], f"sentinel-{experiment_id}"
    if fault == FaultType.crash:
        docker_ctl.start_container(svc["container"], project)
    elif fault in (FaultType.latency, FaultType.timeout):
        toxiproxy.remove_toxic(proxy, toxic)
    else:
        toxiproxy.set_enabled(proxy, True)


def _service_config(adapter: dict, service: str) -> dict:
    for svc in adapter["services"]:
        if svc["name"] == service:
            return svc
    raise AppError(422, "validation_error", f"Unknown service '{service}'")


def start_experiment(db: Session, body: ExperimentCreate) -> ExperimentRecord:
    adapter = repo.get_adapter(db, body.application_id)
    svc = _service_config(adapter, body.service)
    if body.fault_type.value not in svc.get("faults", []):
        raise AppError(
            422, "fault_not_available", f"'{body.fault_type.value}' is not available for '{body.service}'"
        )
    params = _clean_parameters(body.fault_type, body.parameters)

    _ask_gateway(TOOL_FOR_FAULT[body.fault_type], ActionType.inject_fault, body.service, params)

    experiment_id = uuid.uuid4()
    _apply(body.fault_type, experiment_id, svc, adapter.get("compose_project"), params)
    return repo.insert_experiment(
        db, experiment_id, body.application_id, body.service, body.fault_type.value, params, "dashboard"
    )


def clear_experiment(db: Session, experiment_id: uuid.UUID) -> ExperimentRecord:
    exp = repo.get_experiment(db, experiment_id)
    if exp.ended_at is not None:
        raise AppError(409, "experiment_already_cleared", "This experiment was already cleared")

    adapter = repo.get_adapter(db, exp.application_id)
    svc = _service_config(adapter, exp.service)

    _ask_gateway("clear_fault", ActionType.clear_fault, exp.service, {"experiment_id": str(exp.id)})
    _revert(exp.fault_type, exp.id, svc, adapter.get("compose_project"))
    return repo.mark_ended(db, exp.id)