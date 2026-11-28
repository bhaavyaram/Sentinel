"""Read-only lookups of the application's services (tables: applications, services)."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from app.db import SessionLocal


@dataclass(frozen=True)
class ServiceInfo:
    name: str
    type: str  # 'stateless' or 'stateful'
    critical: bool


def load_services(application_id: UUID) -> dict[str, ServiceInfo]:
    with SessionLocal() as db:
        rows = db.execute(
            text("select name, type, critical from services where application_id = :id"),
            {"id": application_id},
        ).all()
    return {row[0]: ServiceInfo(row[0], row[1], bool(row[2])) for row in rows}


def list_application_ids() -> list[UUID]:
    with SessionLocal() as db:
        rows = db.execute(text("select id from applications")).all()
    return [row[0] for row in rows]