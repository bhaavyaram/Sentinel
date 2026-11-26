from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class ParsedSpan:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    service: str
    name: str
    start_ts: datetime
    end_ts: datetime
    status: str  # ok | error | unset


_STATUS = {
    0: "unset",
    1: "ok",
    2: "error",
    "STATUS_CODE_UNSET": "unset",
    "STATUS_CODE_OK": "ok",
    "STATUS_CODE_ERROR": "error",
}


def _nanos_to_datetime(value: Any) -> datetime:
    ns = int(value)
    seconds, remainder = divmod(ns, 1_000_000_000)
    return datetime.fromtimestamp(seconds, tz=timezone.utc) + timedelta(microseconds=remainder // 1000)


def _service_name(resource: dict[str, Any]) -> str | None:
    for attr in resource.get("attributes", []):
        if attr.get("key") == "service.name":
            return attr.get("value", {}).get("stringValue")
    return None


def parse_otlp_traces(payload: dict[str, Any]) -> list[ParsedSpan]:
    """Turn an OTLP/JSON traces payload into a flat list of spans.

    Resources without a service.name and malformed spans are skipped, never raised:
    the data comes from the monitored application and must not be able to break ingestion.
    """
    spans: list[ParsedSpan] = []
    for resource_spans in payload.get("resourceSpans", []):
        service = _service_name(resource_spans.get("resource", {}))
        if not service:
            continue
        for scope_spans in resource_spans.get("scopeSpans", []):
            for raw in scope_spans.get("spans", []):
                try:
                    start = _nanos_to_datetime(raw["startTimeUnixNano"])
                    end = _nanos_to_datetime(raw["endTimeUnixNano"])
                    spans.append(
                        ParsedSpan(
                            trace_id=str(raw["traceId"]),
                            span_id=str(raw["spanId"]),
                            parent_span_id=str(raw["parentSpanId"]) if raw.get("parentSpanId") else None,
                            service=service,
                            name=str(raw.get("name", "")),
                            start_ts=start,
                            end_ts=end,
                            status=_STATUS.get(raw.get("status", {}).get("code", 0), "unset"),
                        )
                    )
                except (KeyError, ValueError, TypeError, OverflowError):
                    continue
    return spans