"""Diagnostics tools (Contracts section 6): read-only, low risk.

Each function returns the tool's `data` dictionary. The gateway will wrap it as
{ data, untrusted: true } (see app/tools/base.py). Everything inside `data` that came
from a container or a trace (log lines, span names) is untrusted text.

application_id is an explicit argument because GatewayRequest has no such field yet.

Edge direction: an edge `source -> target` means "source calls target".
  upstream   = services that call this one (its callers)
  downstream = services this one calls (its dependencies)
"""

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from docker.errors import DockerException
from sqlalchemy import text

from app.db import SessionLocal
from app.monitoring.state import tracker
from app.tools.base import ToolError
from app.tools.containers import find_container

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_MESSAGE_CHARS = 500
MAX_SPANS_PER_TRACE = 50
BUCKET_SECONDS = 10

LEVELS = ("debug", "info", "warn", "error")
METRICS = ("span_count", "error_count", "error_rate", "p95_latency_ms")

_LEVEL_WORDS = {
    "debug": "debug",
    "trace": "debug",
    "info": "info",
    "notice": "info",
    "warn": "warn",
    "warning": "warn",
    "error": "error",
    "err": "error",
    "fail": "error",
    "fatal": "error",
    "critical": "error",
    "panic": "error",
}
_LEVEL_REGEX = re.compile(
    r"\b(debug|trace|info|notice|warn|warning|error|err|fail|fatal|critical|panic)\b", re.I
)
# Docker log line with timestamps=True: "2026-11-28T10:00:01.123456789Z message"
_LOG_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?Z\s?(.*)$")


# --- small helpers -------------------------------------------------------------------


def clamp_limit(limit: Any) -> int:
    """Contracts section 6: limit defaults to 50 and never exceeds 200."""
    if limit is None:
        return DEFAULT_LIMIT
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ToolError("limit must be an integer")
    return min(max(limit, 1), MAX_LIMIT)


def parse_time(value: Any, name: str) -> datetime:
    """Accepts an ISO 8601 string (or datetime). A value without a zone is treated as UTC."""
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            raise ToolError(f"{name} must be an ISO 8601 UTC timestamp") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _check_level(level: Any) -> str | None:
    if level is None:
        return None
    if level not in LEVELS:
        raise ToolError(f"level must be one of: {', '.join(LEVELS)}")
    return level


def detect_level(message: str) -> str:
    """Best-effort log level. Handles JSON logs and 'info:' / 'ERROR' style prefixes."""
    stripped = message.strip()
    if stripped.startswith("{"):
        try:
            obj = json.loads(stripped)
        except ValueError:
            obj = None
        if isinstance(obj, dict):
            for key in ("severity", "level", "levelname"):
                value = obj.get(key)
                if isinstance(value, str) and value.lower() in _LEVEL_WORDS:
                    return _LEVEL_WORDS[value.lower()]
    found = _LEVEL_REGEX.search(message[:60])  # only the start, so "more info" later does not count
    if found:
        return _LEVEL_WORDS[found.group(1).lower()]
    return "info"


def parse_log_line(raw: str) -> dict[str, str] | None:
    found = _LOG_LINE.match(raw.rstrip("\r\n"))
    if found is None:
        return None
    base, fraction, message = found.groups()
    micros = int((fraction or "0")[:6].ljust(6, "0"))
    ts = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S").replace(microsecond=micros, tzinfo=timezone.utc)
    return {"ts": _iso(ts), "level": detect_level(message), "message": message[:MAX_MESSAGE_CHARS]}


def parse_logs(raw_text: str) -> list[dict[str, str]]:
    """Turns Docker's text output into log entries. Lines without a timestamp
    (stack-trace continuations) are attached to the entry before them."""
    entries: list[dict[str, str]] = []
    for raw in raw_text.splitlines():
        entry = parse_log_line(raw)
        if entry is not None:
            entries.append(entry)
        elif entries:
            joined = entries[-1]["message"] + "\n" + raw
            entries[-1]["message"] = joined[:MAX_MESSAGE_CHARS]
    return entries


# --- database access (tests replace these functions with fakes) -----------------------


def _resolve_container(application_id: UUID, service: str) -> tuple[str, str | None]:
    """Returns (docker compose service name, compose project) from the stored adapter."""
    with SessionLocal() as db:
        row = db.execute(
            text("select adapter from applications where id = :id"), {"id": application_id}
        ).first()
    if row is None:
        raise ToolError("unknown application")
    adapter = row[0]
    try:
        for entry in adapter["services"]:
            if entry["name"] == service:
                return entry["container"], adapter.get("compose_project")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ToolError("the stored adapter has an unexpected shape") from exc
    raise ToolError(f"unknown service '{service}'")


def _known_services(application_id: UUID) -> set[str]:
    with SessionLocal() as db:
        rows = db.execute(
            text("select name from services where application_id = :id"), {"id": application_id}
        ).all()
    return {row[0] for row in rows}


def _require_service(application_id: UUID, service: str) -> None:
    if service not in _known_services(application_id):
        raise ToolError(f"unknown service '{service}'")


_METRICS_SQL = """
select to_timestamp(floor(extract(epoch from start_ts) / cast(:bucket as integer))
                    * cast(:bucket as integer)) as bucket,
       count(*) as span_count,
       count(*) filter (where status = 'error') as error_count,
       percentile_cont(0.95) within group
         (order by extract(epoch from (end_ts - start_ts)) * 1000) as p95_ms
from trace_spans
where application_id = :app_id
  and service = :service
  and start_ts >= :since
  and (cast(:until as timestamptz) is null or start_ts < cast(:until as timestamptz))
group by 1
order by 1
"""


def _fetch_metric_rows(
    application_id: UUID, service: str, since: datetime, until: datetime | None
) -> list[tuple]:
    with SessionLocal() as db:
        rows = db.execute(
            text(_METRICS_SQL),
            {
                "app_id": application_id,
                "service": service,
                "since": since,
                "until": until,
                "bucket": BUCKET_SECONDS,
            },
        ).all()
    return [tuple(row) for row in rows]


_TRACES_SQL = """
with recent as (
  select trace_id, max(start_ts) as last_ts
  from trace_spans
  where application_id = :app_id and service = :service and start_ts >= :since
  group by trace_id
  order by last_ts desc
  limit :limit
)
select s.trace_id, s.span_id, s.parent_span_id, s.service, s.name, s.start_ts, s.end_ts, s.status
from trace_spans s
join recent r on r.trace_id = s.trace_id
where s.application_id = :app_id
order by r.last_ts desc, s.start_ts
"""


def _fetch_trace_rows(application_id: UUID, service: str, since: datetime, limit: int) -> list[tuple]:
    with SessionLocal() as db:
        rows = db.execute(
            text(_TRACES_SQL),
            {"app_id": application_id, "service": service, "since": since, "limit": limit},
        ).all()
    return [tuple(row) for row in rows]


def _fetch_edges(application_id: UUID) -> list[tuple[str, str]]:
    with SessionLocal() as db:
        rows = db.execute(
            text("select source, target from dependencies where application_id = :id"),
            {"id": application_id},
        ).all()
    return [(row[0], row[1]) for row in rows]


# --- the five tools -------------------------------------------------------------------


def query_logs(
    application_id: UUID,
    service: str,
    since: str,
    until: str | None = None,
    level: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Docker logs of the service's container. Logs of an exited container stay readable."""
    since_dt = parse_time(since, "since")
    until_dt = parse_time(until, "until") if until else None
    wanted = _check_level(level)
    limit = clamp_limit(limit)

    compose_service, project = _resolve_container(application_id, service)
    container = find_container(compose_service, project)

    options: dict[str, Any] = {"timestamps": True, "since": since_dt}
    if until_dt is not None:
        options["until"] = until_dt
    try:
        raw = container.logs(**options)
    except DockerException as exc:
        raise ToolError(f"Docker could not read logs of '{service}': {exc}") from exc

    lines = parse_logs(raw.decode("utf-8", errors="replace"))
    if wanted is not None:
        lines = [line for line in lines if line["level"] == wanted]
    return {"lines": lines[-limit:]}  # the most recent lines, oldest first


def query_metrics(
    application_id: UUID, service: str, metric: str, since: str, until: str | None = None
) -> dict[str, Any]:
    """Metrics derived from trace_spans in 10-second buckets (decision Q1).

    A bucket with no spans has no point, so a crashed service shows a gap, and a
    service that sends no traces returns an empty series.
    """
    if metric not in METRICS:
        raise ToolError(f"metric must be one of: {', '.join(METRICS)}")
    since_dt = parse_time(since, "since")
    until_dt = parse_time(until, "until") if until else None
    _require_service(application_id, service)

    points = []
    for bucket, span_count, error_count, p95_ms in _fetch_metric_rows(
        application_id, service, since_dt, until_dt
    ):
        if metric == "span_count":
            value: float = int(span_count)
        elif metric == "error_count":
            value = int(error_count)
        elif metric == "error_rate":
            value = round(int(error_count) / int(span_count), 4) if span_count else 0.0
        else:
            value = round(float(p95_ms), 1) if p95_ms is not None else 0.0
        points.append({"ts": _iso(bucket), "value": value})
    return {"points": points[-MAX_LIMIT:]}


def get_traces(
    application_id: UUID, service: str, since: str, limit: int | None = None
) -> dict[str, Any]:
    """Recent traces that include a span of this service, with all spans of each trace."""
    since_dt = parse_time(since, "since")
    limit = clamp_limit(limit)
    _require_service(application_id, service)

    traces: dict[str, list[dict[str, Any]]] = {}
    for trace_id, span_id, parent, span_service, name, start, end, status in _fetch_trace_rows(
        application_id, service, since_dt, limit
    ):
        spans = traces.setdefault(trace_id, [])
        if len(spans) < MAX_SPANS_PER_TRACE:
            spans.append(
                {
                    "span_id": span_id,
                    "parent_span_id": parent,
                    "service": span_service,
                    "name": name,
                    "start_ts": _iso(start),
                    "duration_ms": round((end - start).total_seconds() * 1000, 1),
                    "status": status,
                }
            )
    return {"traces": [{"trace_id": tid, "spans": spans} for tid, spans in traces.items()]}


def get_service_status(application_id: UUID, service: str) -> dict[str, Any]:
    _require_service(application_id, service)
    return {"health": tracker.get(application_id, service).value, "last_check": None}


def get_dependencies(application_id: UUID, service: str) -> dict[str, Any]:
    _require_service(application_id, service)
    edges = _fetch_edges(application_id)
    upstream = sorted({source for source, target in edges if target == service})
    downstream = sorted({target for source, target in edges if source == service})
    return {"upstream": upstream, "downstream": downstream}

def list_services(application_id: UUID) -> list[str]:
    """Service names of the application (agents use it to validate what a model returns)."""
    return sorted(_known_services(application_id))