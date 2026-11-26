import json
import uuid

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.schemas import AdapterFile
from app.schemas.applications import (
    ApplicationMap,
    ApplicationSummary,
    AvailableExperiment,
    AvailableExperiments,
    MapEdge,
    MapNode,
)
from app.schemas.enums import ServiceHealth


def _not_found(app_id: uuid.UUID) -> AppError:
    return AppError(404, "application_not_found", f"No application with id {app_id}")


def create_application(db: Session, adapter: AdapterFile) -> uuid.UUID:
    app_id = uuid.uuid4()
    adapter_json = json.dumps(adapter.model_dump(mode="json", by_alias=True))

    try:
        db.execute(
            text(
                "insert into applications (id, name, adapter, status) "
                "values (:id, :name, cast(:adapter as jsonb), :status)"
            ),
            {"id": app_id, "name": adapter.app, "adapter": adapter_json, "status": "connected"},
        )
        for svc in adapter.services:
            db.execute(
                text(
                    "insert into services (id, application_id, name, type, critical, health_endpoint) "
                    "values (:id, :application_id, :name, :type, :critical, :health_endpoint)"
                ),
                {
                    "id": uuid.uuid4(),
                    "application_id": app_id,
                    "name": svc.name,
                    "type": svc.type.value,
                    "critical": svc.critical,
                    "health_endpoint": svc.health,
                },
            )
        seen_edges: set[tuple[str, str]] = set()
        for dep in adapter.declared_dependencies:
            edge = (dep.from_, dep.to)
            if edge in seen_edges:
                continue
            seen_edges.add(edge)
            db.execute(
                text(
                    "insert into dependencies (id, application_id, source, target, evidence) "
                    "values (:id, :application_id, :source, :target, 'declared')"
                ),
                {"id": uuid.uuid4(), "application_id": app_id, "source": dep.from_, "target": dep.to},
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "application_exists", f"Application '{adapter.app}' already exists")

    return app_id


_SUMMARY_SQL = (
    "select a.id, a.name, a.status, a.created_at, "
    "(select count(*) from services s where s.application_id = a.id) as service_count "
    "from applications a"
)


def get_application_summary(db: Session, app_id: uuid.UUID) -> ApplicationSummary:
    row = db.execute(text(_SUMMARY_SQL + " where a.id = :id"), {"id": app_id}).mappings().first()
    if row is None:
        raise _not_found(app_id)
    return ApplicationSummary(**row)


def list_applications(db: Session) -> list[ApplicationSummary]:
    rows = db.execute(text(_SUMMARY_SQL + " order by a.created_at")).mappings().all()
    return [ApplicationSummary(**row) for row in rows]


def get_map(db: Session, app_id: uuid.UUID) -> ApplicationMap:
    get_application_summary(db, app_id)  # raises 404 if missing

    services = db.execute(
        text(
            "select name, type, critical, health_endpoint from services "
            "where application_id = :id order by name"
        ),
        {"id": app_id},
    ).mappings().all()
    edges = db.execute(
        text(
            "select source, target, evidence from dependencies "
            "where application_id = :id order by source, target"
        ),
        {"id": app_id},
    ).mappings().all()

    return ApplicationMap(
        application_id=app_id,
        nodes=[MapNode(**s, health=ServiceHealth.unknown) for s in services],
        edges=[MapEdge(**e) for e in edges],
    )


def get_available_experiments(db: Session, app_id: uuid.UUID) -> AvailableExperiments:
    row = db.execute(
        text("select adapter from applications where id = :id"), {"id": app_id}
    ).first()
    if row is None:
        raise _not_found(app_id)

    adapter = row[0]
    experiments = [
        AvailableExperiment(service=svc["name"], fault_type=fault)
        for svc in adapter["services"]
        for fault in svc.get("faults", [])
    ]
    return AvailableExperiments(application_id=app_id, experiments=experiments)