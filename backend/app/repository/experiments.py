import json
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.errors import AppError
from app.schemas.experiments import ExperimentRecord

_COLUMNS = "id, application_id, service, fault_type, parameters, started_at, ended_at, initiated_by"


def get_adapter(db: Session, app_id: uuid.UUID) -> dict:
    row = db.execute(text("select adapter from applications where id = :id"), {"id": app_id}).first()
    if row is None:
        raise AppError(404, "application_not_found", f"No application with id {app_id}")
    return row[0]


def insert_experiment(
    db: Session,
    experiment_id: uuid.UUID,
    app_id: uuid.UUID,
    service: str,
    fault_type: str,
    parameters: dict,
    initiated_by: str,
) -> ExperimentRecord:
    row = db.execute(
        text(
            "insert into experiments (id, application_id, service, fault_type, parameters, "
            "started_at, initiated_by) "
            "values (:id, :app_id, :service, :fault_type, cast(:parameters as jsonb), now(), :initiated_by) "
            f"returning {_COLUMNS}"
        ),
        {
            "id": experiment_id,
            "app_id": app_id,
            "service": service,
            "fault_type": fault_type,
            "parameters": json.dumps(parameters),
            "initiated_by": initiated_by,
        },
    ).mappings().one()
    db.commit()
    return ExperimentRecord(**row)


def get_experiment(db: Session, experiment_id: uuid.UUID) -> ExperimentRecord:
    row = db.execute(
        text(f"select {_COLUMNS} from experiments where id = :id"), {"id": experiment_id}
    ).mappings().first()
    if row is None:
        raise AppError(404, "experiment_not_found", f"No experiment with id {experiment_id}")
    return ExperimentRecord(**row)


def mark_ended(db: Session, experiment_id: uuid.UUID) -> ExperimentRecord:
    db.execute(text("update experiments set ended_at = now() where id = :id"), {"id": experiment_id})
    db.commit()
    return get_experiment(db, experiment_id)