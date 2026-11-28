"""Milestone I2 check: a real RootCauseReport from the real stack.

Usage (from the backend folder, venv active, backend + Docker + Postgres running):
    python scripts\\try_investigator.py <application_id> <service>

Service health lives in the memory of the backend process, which this script cannot see,
so get_service_status is read from the backend's map endpoint here. Inside the backend
process the agents read the tracker directly.
"""

import sys
from pathlib import Path
from uuid import UUID, uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.errors import AgentEscalation  # noqa: E402
from app.agents.investigator import investigate  # noqa: E402
from app.agents.llm import GroqClient  # noqa: E402
from app.agents.toolcall import direct_diagnostics  # noqa: E402
from app.tools.base import ToolError  # noqa: E402

API = "http://localhost:8000/api/v1"


def make_call_tool(application_id: UUID):
    direct = direct_diagnostics(application_id)

    def call(tool: str, **args):
        if tool == "get_service_status":
            response = httpx.get(f"{API}/applications/{application_id}/map", timeout=10)
            response.raise_for_status()
            for node in response.json()["nodes"]:
                if node["name"] == args["service"]:
                    return {"health": node["health"], "last_check": None}
            raise ToolError(f"unknown service '{args['service']}'")
        return direct(tool, **args)

    return call


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python scripts\\try_investigator.py <application_id> <service>")
        return 1
    application_id = UUID(sys.argv[1])
    try:
        draft = investigate(
            application_id,
            sys.argv[2],
            GroqClient(),
            call_tool=make_call_tool(application_id),
        )
    except AgentEscalation as exc:
        print(f"ESCALATED TO A HUMAN: {exc}")
        return 2
    # The orchestrator would use the real incident id; a random one is enough for this check.
    print(draft.finalize(uuid4()).model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())