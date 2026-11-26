from datetime import datetime, timezone

from app.telemetry.otlp import parse_otlp_traces

TRACE = "a" * 32
PARENT = "1" * 16
CHILD = "2" * 16


def resource(service: str | None, spans: list[dict]) -> dict:
    attrs = [] if service is None else [{"key": "service.name", "value": {"stringValue": service}}]
    return {"resource": {"attributes": attrs}, "scopeSpans": [{"spans": spans}]}


PAYLOAD = {
    "resourceSpans": [
        resource(
            "frontend",
            [
                {
                    "traceId": TRACE,
                    "spanId": PARENT,
                    "name": "GET /product",
                    "startTimeUnixNano": "1700000000000000000",
                    "endTimeUnixNano": "1700000000500000000",
                    "status": {"code": 0},
                }
            ],
        ),
        resource(
            "checkoutservice",
            [
                {
                    "traceId": TRACE,
                    "spanId": CHILD,
                    "parentSpanId": PARENT,
                    "name": "PlaceOrder",
                    "startTimeUnixNano": "1700000000100000000",
                    "endTimeUnixNano": "1700000000200000000",
                    "status": {"code": 2},
                }
            ],
        ),
    ]
}


def test_parses_spans_with_service_names():
    spans = parse_otlp_traces(PAYLOAD)
    assert [s.service for s in spans] == ["frontend", "checkoutservice"]


def test_parent_link_and_missing_parent():
    parent, child = parse_otlp_traces(PAYLOAD)
    assert parent.parent_span_id is None
    assert child.parent_span_id == PARENT


def test_error_status_is_mapped():
    parent, child = parse_otlp_traces(PAYLOAD)
    assert parent.status == "unset"
    assert child.status == "error"


def test_timestamps_are_utc():
    parent, _ = parse_otlp_traces(PAYLOAD)
    assert parent.start_ts == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
    assert parent.end_ts == datetime(2023, 11, 14, 22, 13, 20, 500000, tzinfo=timezone.utc)


def test_resource_without_service_name_and_malformed_span_are_skipped():
    payload = {
        "resourceSpans": [
            resource(None, [{"traceId": TRACE, "spanId": PARENT}]),
            resource("frontend", [{"traceId": TRACE, "spanId": PARENT, "name": "no times"}]),
        ]
    }
    assert parse_otlp_traces(payload) == []


def test_empty_payload():
    assert parse_otlp_traces({}) == []