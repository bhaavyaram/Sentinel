import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import events
from app.db import get_db
from app.errors import AppError
from app.events import EventPublishError
from app.policy.io import parse_policy_body
from app.repository import policies as repo
from app.schemas import Actor, EventType, Policy, PolicyBody

log = logging.getLogger(__name__)
router = APIRouter(prefix="/policies", tags=["policies"])

# There is no login yet. Step 8c adds admin and approver roles.
ADMIN = "admin"


def _announce(db: Session, policy: Policy, previous_version: int | None) -> None:
    """Policies are global, events belong to an application: publish once per application."""
    application_ids = [row[0] for row in db.execute(text("select id from applications")).all()]
    for application_id in application_ids:
        try:
            events.publish(
                application_id,
                EventType.policy_changed,
                Actor.human,
                {
                    "from_version": previous_version,
                    "to_version": policy.version,
                    "changed_by": policy.created_by,
                },
                policy_version=policy.version,
            )
        except EventPublishError:
            # The policy is already saved and audited, so do not fail the request.
            log.exception("could not publish policy_changed for application %s", application_id)


@router.get("/current", response_model=Policy)
def get_current_policy(db: Session = Depends(get_db)) -> Policy:
    return repo.get_current(db)


@router.get("/export", response_model=Policy)
def export_policy(db: Session = Depends(get_db)) -> Policy:
    return repo.get_current(db)


@router.get("", response_model=list[Policy])
def list_policies(db: Session = Depends(get_db)) -> list[Policy]:
    return repo.list_policies(db)


@router.post("", response_model=Policy, status_code=201)
def create_policy(body: PolicyBody, db: Session = Depends(get_db)) -> Policy:
    policy, previous = repo.create_version(db, body, ADMIN, "edit")
    _announce(db, policy, previous)
    return policy


@router.post("/import", response_model=Policy, status_code=201)
async def import_policy(request: Request, db: Session = Depends(get_db)) -> Policy:
    try:
        data = await request.json()
    except ValueError:
        raise AppError(400, "invalid_json", "Request body is not valid JSON")
    body = parse_policy_body(data)
    policy, previous = repo.create_version(db, body, ADMIN, "import")
    _announce(db, policy, previous)
    return policy


@router.post("/{version}/restore", response_model=Policy, status_code=201)
def restore_policy(version: int, db: Session = Depends(get_db)) -> Policy:
    old = repo.get_version(db, version)
    body = PolicyBody.model_validate(
        old.model_dump(mode="json", exclude={"version", "created_by", "created_at"})
    )
    policy, previous = repo.create_version(db, body, ADMIN, "restore", {"restored_from": version})
    _announce(db, policy, previous)
    return policy