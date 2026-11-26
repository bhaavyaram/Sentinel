import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import AppError
from app.repository import traces as repo
from app.telemetry.otlp import parse_otlp_traces

router = APIRouter(prefix="/ingest", tags=["ingest"])

MAX_PAYLOAD_BYTES = 10_000_000


@router.post("/traces")
async def ingest_traces(request: Request, db: Session = Depends(get_db)) -> dict:
    """Receives OTLP/JSON traces from the OpenTelemetry collector."""
    app_name = request.headers.get("x-sentinel-app")
    if not app_name:
        raise AppError(400, "missing_application", "The X-Sentinel-App header is required")

    raw = await request.body()
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise AppError(413, "payload_too_large", "Trace payload is larger than 10 MB")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AppError(400, "invalid_payload", "Body must be OTLP JSON")
    if not isinstance(payload, dict):
        raise AppError(400, "invalid_payload", "Body must be an OTLP JSON object")

    app_id = repo.get_application_id(db, app_name)
    spans = parse_otlp_traces(payload)
    repo.store_spans(db, app_id, spans)
    repo.upgrade_edges(db, app_id, spans)
    db.commit()
    return {}