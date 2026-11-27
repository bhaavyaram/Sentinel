"""Health monitor: one sweep checks every service of every connected application."""

import logging
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import docker
from sqlalchemy import text

from app import events
from app.db import SessionLocal
from app.events import EventPublishError
from app.monitoring import probes, state
from app.schemas import Actor, EventType, ServiceHealth

log = logging.getLogger(__name__)

MAX_PROBE_THREADS = 8

_docker_unreachable = False  # so a Docker outage is logged once, not every 3 seconds


def classify(container_status: str | None, probe_result: bool | None) -> ServiceHealth:
    """Container state is the primary signal; the probe only confirms a running container."""
    if container_status is None:
        return ServiceHealth.unknown
    if container_status == "restarting":
        return ServiceHealth.degraded
    if container_status != "running":
        return ServiceHealth.down
    if probe_result is False:
        return ServiceHealth.degraded
    return ServiceHealth.healthy


def _load_applications() -> list[tuple[UUID, dict]]:
    with SessionLocal() as db:
        rows = db.execute(text("select id, adapter from applications")).all()
    return [(row[0], row[1]) for row in rows]


def _container_states() -> dict[tuple[str | None, str], str]:
    """One Docker call per sweep: {(compose project, compose service): container status}."""
    client = docker.from_env()
    try:
        containers = client.containers.list(
            all=True, filters={"label": "com.docker.compose.service"}
        )
        return {
            (c.labels.get("com.docker.compose.project"), c.labels["com.docker.compose.service"]): c.status
            for c in containers
        }
    finally:
        client.close()


def _status_for(
    states: dict[tuple[str | None, str], str], project: str | None, container: str
) -> str | None:
    for (proj, service), status in states.items():
        if service == container and (project is None or proj == project):
            return status
    return None


def _record(app_id: UUID, service: str, raw: ServiceHealth) -> None:
    change = state.tracker.observe(app_id, service, raw)
    if change is None:
        return
    old, new = change
    try:
        events.publish(
            app_id,
            EventType.service_health_changed,
            Actor.system,
            {"service": service, "from": old.value, "to": new.value},
        )
    except EventPublishError:
        log.exception("could not publish health change for %s", service)


def sweep_once() -> None:
    global _docker_unreachable

    applications = _load_applications()
    if not applications:
        return

    try:
        states = _container_states()
    except Exception as exc:  # Docker Desktop stopped, pipe error, and so on
        if not _docker_unreachable:
            log.warning("health monitor cannot reach Docker, keeping last known health: %s", exc)
            _docker_unreachable = True
        return
    _docker_unreachable = False

    # Phase 1: containers that are not running need no probe, so report them right away.
    to_probe: list[tuple[UUID, dict]] = []
    for app_id, adapter in applications:
        project = adapter.get("compose_project")
        for svc in adapter["services"]:
            status = _status_for(states, project, svc["container"])
            if status == "running":
                to_probe.append((app_id, svc))
            else:
                _record(app_id, svc["name"], classify(status, None))

    # Phase 2: probe the running containers in parallel, so one sweep takes about one timeout.
    if not to_probe:
        return
    with ThreadPoolExecutor(max_workers=MAX_PROBE_THREADS) as pool:
        results = list(pool.map(lambda item: probes.probe(item[1].get("health")), to_probe))
    for (app_id, svc), result in zip(to_probe, results):
        _record(app_id, svc["name"], classify("running", result))