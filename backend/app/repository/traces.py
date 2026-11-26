import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.errors import AppError
from app.telemetry.otlp import ParsedSpan


def get_application_id(db: Session, name: str) -> uuid.UUID:
    row = db.execute(text("select id from applications where name = :name"), {"name": name}).first()
    if row is None:
        raise AppError(404, "application_not_found", f"No application named '{name}'")
    return row[0]


def store_spans(db: Session, app_id: uuid.UUID, spans: list[ParsedSpan]) -> None:
    if not spans:
        return
    db.execute(
        text(
            "insert into trace_spans "
            "(application_id, trace_id, span_id, parent_span_id, service, name, start_ts, end_ts, status) "
            "values (:application_id, :trace_id, :span_id, :parent_span_id, :service, :name, "
            ":start_ts, :end_ts, :status) "
            "on conflict do nothing"
        ),
        [
            {
                "application_id": app_id,
                "trace_id": s.trace_id,
                "span_id": s.span_id,
                "parent_span_id": s.parent_span_id,
                "service": s.service,
                "name": s.name,
                "start_ts": s.start_ts,
                "end_ts": s.end_ts,
                "status": s.status,
            }
            for s in spans
        ],
    )


_UPGRADE_EDGES_SQL = """
insert into dependencies (id, application_id, source, target, evidence)
select gen_random_uuid(), :app_id, p.service, c.service, 'trace'
from trace_spans c
join trace_spans p
  on p.application_id = c.application_id
 and p.trace_id = c.trace_id
 and p.span_id = c.parent_span_id
where c.application_id = :app_id
  and p.service <> c.service
  and (c.span_id = any(:span_ids) or p.span_id = any(:span_ids))
  and p.service in (select name from services where application_id = :app_id)
  and c.service in (select name from services where application_id = :app_id)
group by p.service, c.service
on conflict (application_id, source, target) do update set evidence = 'trace'
"""


def upgrade_edges(db: Session, app_id: uuid.UUID, spans: list[ParsedSpan]) -> None:
    """A caller span (service A) that is the parent of a callee span (service B) means A -> B.

    New edges are stored with evidence 'trace'; an existing 'declared' edge is upgraded.
    Declared edges are never deleted.
    """
    if not spans:
        return
    db.execute(text(_UPGRADE_EDGES_SQL), {"app_id": app_id, "span_ids": [s.span_id for s in spans]})