"""Manual check of the Diagnostics tools against the running stack.

Usage (from the backend folder, venv active):
    python scripts\\try_diagnostics.py <application_id> <service>
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tools import diagnostics as d  # noqa: E402
from app.tools.base import ToolError  # noqa: E402


def show(title: str, call) -> None:
    print(f"\n=== {title} ===")
    try:
        print(json.dumps(call(), indent=2, default=str))
    except ToolError as exc:
        print(f"ToolError: {exc}")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python scripts\\try_diagnostics.py <application_id> <service>")
        return 1
    app_id = UUID(sys.argv[1])
    service = sys.argv[2]
    since = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()

    show("get_service_status", lambda: d.get_service_status(app_id, service))
    show("get_dependencies", lambda: d.get_dependencies(app_id, service))
    show("query_logs (last 5 lines)", lambda: d.query_logs(app_id, service, since, limit=5))
    show("query_metrics (span_count)", lambda: d.query_metrics(app_id, service, "span_count", since))
    show("get_traces (2 traces)", lambda: d.get_traces(app_id, service, since, limit=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())