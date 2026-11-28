from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.monitoring.state import tracker
from app.schemas import ServiceHealth
from app.tools import diagnostics as d
from app.tools.base import ToolError

APP_ID = uuid4()
SINCE = "2026-11-28T10:00:00Z"
T0 = datetime(2026, 11, 28, 10, 0, 0, tzinfo=timezone.utc)

LOGS = (
    "2026-11-28T10:00:01.123456789Z info: Cart started\n"
    '2026-11-28T10:00:02.000000000Z {"severity":"error","message":"redis connection refused"}\n'
    "2026-11-28T10:00:03.500000000Z fail: unhandled exception\n"
    "   at Cart.Run()\n"
    "2026-11-28T10:00:04.000000000Z plain line\n"
)


class FakeContainer:
    def __init__(self, text: str) -> None:
        self._text = text
        self.options: dict = {}

    def logs(self, **options):
        self.options = options
        return self._text.encode("utf-8")


def _patch_logs(monkeypatch, text: str = LOGS) -> FakeContainer:
    container = FakeContainer(text)
    monkeypatch.setattr(d, "_resolve_container", lambda app_id, service: ("cartservice", "online-boutique"))
    monkeypatch.setattr(d, "find_container", lambda compose_service, project: container)
    return container


def _patch_known(monkeypatch) -> None:
    monkeypatch.setattr(d, "_known_services", lambda app_id: {"cartservice"})


def test_parse_logs_detects_levels_and_joins_continuation_lines():
    lines = d.parse_logs(LOGS)
    assert [line["level"] for line in lines] == ["info", "error", "error", "info"]
    assert lines[0]["ts"] == "2026-11-28T10:00:01.123456Z"
    assert "at Cart.Run()" in lines[2]["message"]


def test_query_logs_parses_lines_and_passes_time_window(monkeypatch):
    container = _patch_logs(monkeypatch)
    result = d.query_logs(APP_ID, "cartservice", SINCE)
    assert len(result["lines"]) == 4
    assert container.options["timestamps"] is True
    assert container.options["since"] == datetime(2026, 11, 28, 10, 0, tzinfo=timezone.utc)
    assert "until" not in container.options


def test_query_logs_level_filter(monkeypatch):
    _patch_logs(monkeypatch)
    result = d.query_logs(APP_ID, "cartservice", SINCE, level="error")
    assert len(result["lines"]) == 2


def test_query_logs_limit_keeps_most_recent_lines(monkeypatch):
    _patch_logs(monkeypatch)
    result = d.query_logs(APP_ID, "cartservice", SINCE, limit=2)
    assert result["lines"][0]["message"].startswith("fail:")
    assert result["lines"][1]["message"] == "plain line"


def test_query_logs_rejects_bad_input(monkeypatch):
    _patch_logs(monkeypatch)
    with pytest.raises(ToolError):
        d.query_logs(APP_ID, "cartservice", SINCE, level="loud")
    with pytest.raises(ToolError):
        d.query_logs(APP_ID, "cartservice", "not a time")


@pytest.mark.parametrize("given, expected", [(None, 50), (0, 1), (7, 7), (500, 200)])
def test_clamp_limit(given, expected):
    assert d.clamp_limit(given) == expected


def test_clamp_limit_rejects_non_integer():
    with pytest.raises(ToolError):
        d.clamp_limit("x")


def test_query_metrics_buckets(monkeypatch):
    _patch_known(monkeypatch)
    rows = [(T0, 10, 2, 120.456), (T0 + timedelta(seconds=10), 4, 0, 30.0)]
    monkeypatch.setattr(d, "_fetch_metric_rows", lambda app_id, service, since, until: rows)

    errors = d.query_metrics(APP_ID, "cartservice", "error_rate", SINCE)
    assert errors["points"] == [
        {"ts": "2026-11-28T10:00:00.000000Z", "value": 0.2},
        {"ts": "2026-11-28T10:00:10.000000Z", "value": 0.0},
    ]
    p95 = d.query_metrics(APP_ID, "cartservice", "p95_latency_ms", SINCE)
    assert p95["points"][0]["value"] == 120.5
    count = d.query_metrics(APP_ID, "cartservice", "span_count", SINCE)
    assert count["points"][0]["value"] == 10


def test_query_metrics_rejects_unknown_metric(monkeypatch):
    _patch_known(monkeypatch)
    with pytest.raises(ToolError):
        d.query_metrics(APP_ID, "cartservice", "cpu", SINCE)


def test_diagnostics_reject_unknown_service(monkeypatch):
    _patch_known(monkeypatch)
    with pytest.raises(ToolError):
        d.query_metrics(APP_ID, "nope", "span_count", SINCE)
    with pytest.raises(ToolError):
        d.get_traces(APP_ID, "nope", SINCE)
    with pytest.raises(ToolError):
        d.get_service_status(APP_ID, "nope")
    with pytest.raises(ToolError):
        d.get_dependencies(APP_ID, "nope")


def test_get_traces_groups_spans_by_trace(monkeypatch):
    _patch_known(monkeypatch)
    ms = lambda n: T0 + timedelta(milliseconds=n)  # noqa: E731
    rows = [
        ("t1", "s1", None, "frontend", "GET /cart", T0, ms(120), "ok"),
        ("t1", "s2", "s1", "cartservice", "GetCart", ms(10), ms(90), "error"),
        ("t2", "s3", None, "checkout", "PlaceOrder", T0, ms(50), "ok"),
    ]
    monkeypatch.setattr(d, "_fetch_trace_rows", lambda app_id, service, since, limit: rows)

    result = d.get_traces(APP_ID, "cartservice", SINCE)
    assert [t["trace_id"] for t in result["traces"]] == ["t1", "t2"]
    first = result["traces"][0]["spans"]
    assert len(first) == 2
    assert first[0]["parent_span_id"] is None
    assert first[1]["parent_span_id"] == "s1"
    assert first[1]["duration_ms"] == 80.0


def test_get_service_status_reads_tracker(monkeypatch):
    _patch_known(monkeypatch)
    tracker.observe(APP_ID, "cartservice", ServiceHealth.down)
    assert d.get_service_status(APP_ID, "cartservice") == {"health": "down", "last_check": None}


def test_get_dependencies_directions(monkeypatch):
    _patch_known(monkeypatch)
    edges = [("frontend", "cartservice"), ("checkout", "cartservice"), ("cartservice", "redis-cart")]
    monkeypatch.setattr(d, "_fetch_edges", lambda app_id: edges)
    result = d.get_dependencies(APP_ID, "cartservice")
    assert result == {"upstream": ["checkout", "frontend"], "downstream": ["redis-cart"]}