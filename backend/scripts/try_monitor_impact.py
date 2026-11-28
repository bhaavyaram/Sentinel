"""Mini integration check: crash -> Monitor opens an incident -> Investigator -> Impact.

Usage (from the backend folder, venv active, backend + Docker + Postgres running):
    python scripts\\try_monitor_impact.py <application_id>
Leave it running, then crash a service from another terminal. It stops after the first incident.
Health is read from the backend's map endpoint because the tracker lives in the backend process.
"""

import sys
import time
from pathlib import Path
from uuid import UUID

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.catalog import load_services  # noqa: E402
from app.agents.errors import AgentEscalation  # noqa: E402
from app.agents.impact import analyze_impact  # noqa: E402
from app.agents.incidents import FakeIncidents  # noqa: E402
from app.agents.investigator import investigate  # noqa: E402
from app.agents.llm import GroqClient  # noqa: E402
from app.agents.monitor import Monitor  # noqa: E402
from app.agents.toolcall import direct_diagnostics  # noqa: E402
from app.schemas.enums import IncidentStatus, ServiceHealth  # noqa: E402
from app.tools.base import ToolError  # noqa: E402

API = "http://localhost:8000/api/v1"
TIMEOUT_S = 180


def refresh_health(application_id: UUID) -> dict[str, ServiceHealth]:
    response = httpx.get(f"{API}/applications/{application_id}/map", timeout=10)
    response.raise_for_status()
    return {node["name"]: ServiceHealth(node["health"]) for node in response.json()["nodes"]}


def make_call_tool(application_id: UUID, health: dict[str, ServiceHealth]):
    direct = direct_diagnostics(application_id)

    def call(tool: str, **args):
        if tool == "get_service_status":
            if args["service"] not in health:
                raise ToolError(f"unknown service '{args['service']}'")
            return {"health": health[args["service"]].value, "last_check": None}
        return direct(tool, **args)

    return call


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python scripts\\try_monitor_impact.py <application_id>")
        return 1
    application_id = UUID(sys.argv[1])
    services = load_services(application_id)
    incidents = FakeIncidents()
    health = refresh_health(application_id)
    done: list[bool] = []

    def on_incident(app_id: UUID, incident_id: UUID, service: str) -> None:
        print(f"\nINCIDENT {incident_id} opened for {service}")
        incidents.set_status(incident_id, IncidentStatus.investigating)
        call_tool = make_call_tool(app_id, health)
        try:
            root = investigate(app_id, service, GroqClient(), call_tool=call_tool)
            top = root.hypotheses[0]
            print(f"ROOT CAUSE ({top.confidence}): {top.service}: {top.cause}")
            impact = analyze_impact(app_id, incident_id, service, root, GroqClient(), call_tool=call_tool)
            print(impact.finalize(incident_id).model_dump_json(indent=2))
        except AgentEscalation as exc:
            print(f"ESCALATED TO A HUMAN: {exc}")
        done.append(True)

    monitor = Monitor(incidents, get_health=lambda app_id, name: health.get(name, ServiceHealth.unknown), on_incident=on_incident)
    print("Watching health every 3 seconds. Crash a service now (see the instructions).")
    started = time.time()
    while not done and time.time() - started < TIMEOUT_S:
        health.update(refresh_health(application_id))
        monitor.check(application_id, services.values())
        time.sleep(3)
    if not done:
        print("No incident was opened within the time limit.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())