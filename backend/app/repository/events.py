import json
import uuid
from typing import Any

from sqlalchemy import text

from app.db import SessionLocal
from app.schemas import SentinelEvent

_FIELDS = "id as event_id, ts, application_id, incident_id, actor, type, payload, policy_version"


def _to_event(row: Any) -> tuple[int, SentinelEvent]:
    data = dict(row)
    seq = data.pop("seq")
    return seq, SentinelEvent(**data)


def insert_event(
    application_id: uuid.UUID,
    incident_id: uuid.UUID | None,
    actor: str,
    event_type: str,
    payload: dict,
    policy_version: int | None,
) -> tuple[int, SentinelEvent]:
    """Stores one event in its own transaction. Returns (seq, event)."""
    with SessionLocal() as db:
        row = db.execute(
            text(
                "insert into incident_events "
                "(id, application_id, incident_id, ts, actor, type, payload, policy_version) "
                "values (:id, :application_id, :incident_id, now(), :actor, :type, "
                "cast(:payload as jsonb), :policy_version) "
                f"returning seq, {_FIELDS}"
            ),
            {
                "id": uuid.uuid4(),
                "application_id": application_id,
                "incident_id": incident_id,
                "actor": actor,
                "type": event_type,
                "payload": json.dumps(payload),
                "policy_version": policy_version,
            },
        ).mappings().one()
        db.commit()
    return _to_event(row)


def get_seq(application_id: uuid.UUID, event_id: uuid.UUID) -> int | None:
    with SessionLocal() as db:
        row = db.execute(
            text("select seq from incident_events where id = :id and application_id = :app"),
            {"id": event_id, "app": application_id},
        ).first()
    return None if row is None else row[0]


def list_after(
    application_id: uuid.UUID, after_seq: int, limit: int = 500
) -> list[tuple[int, SentinelEvent]]:
    with SessionLocal() as db:
        rows = db.execute(
            text(
                f"select seq, {_FIELDS} from incident_events "
                "where application_id = :app and seq > :after order by seq limit :limit"
            ),
            {"app": application_id, "after": after_seq, "limit": limit},
        ).mappings().all()
    return [_to_event(r) for r in rows]