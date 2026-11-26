import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.adapters.loader import MAX_ADAPTER_BYTES, AdapterError, parse_adapter
from app.db import get_db
from app.errors import AppError
from app.repository import applications as repo
from app.schemas.applications import (
    ApplicationMap,
    ApplicationSummary,
    AvailableExperiments,
)

router = APIRouter(prefix="/applications", tags=["applications"])

# Tells the /docs page that this endpoint takes raw YAML text as its body.
YAML_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "application/x-yaml": {"schema": {"type": "string"}},
            "text/plain": {"schema": {"type": "string"}},
        },
    }
}


@router.post("", response_model=ApplicationSummary, status_code=201, openapi_extra=YAML_BODY)
async def upload_adapter(request: Request, db: Session = Depends(get_db)) -> ApplicationSummary:
    raw = await request.body()
    if len(raw) > MAX_ADAPTER_BYTES:
        raise AppError(413, "adapter_too_large", "Adapter file is larger than 1 MB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise AppError(400, "invalid_encoding", "Adapter file must be UTF-8 text")

    try:
        adapter = parse_adapter(text)
    except AdapterError as exc:
        raise AppError(422, "invalid_adapter", str(exc))

    app_id = repo.create_application(db, adapter)
    return repo.get_application_summary(db, app_id)


@router.get("", response_model=list[ApplicationSummary])
def list_applications(db: Session = Depends(get_db)) -> list[ApplicationSummary]:
    return repo.list_applications(db)


@router.get("/{application_id}/map", response_model=ApplicationMap)
def get_application_map(application_id: uuid.UUID, db: Session = Depends(get_db)) -> ApplicationMap:
    return repo.get_map(db, application_id)


@router.get("/{application_id}/experiments/available", response_model=AvailableExperiments)
def get_available_experiments(
    application_id: uuid.UUID, db: Session = Depends(get_db)
) -> AvailableExperiments:
    return repo.get_available_experiments(db, application_id)