import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.errors import AppError
from app.policy import presets
from app.schemas import Policy, PolicyBody

_COLUMNS = "version, body, created_by, created_at"


def _to_policy(row: Any) -> Policy:
    return Policy.model_validate(
        {
            **row["body"],
            "version": row["version"],
            "created_by": row["created_by"],
            "created_at": row["created_at"],
        }
    )


def create_version(
    db: Session,
    body: PolicyBody,
    created_by: str,
    source: str,
    extra: dict | None = None,
) -> tuple[Policy, int | None]:
    """Saves a new policy version and its audit row in one transaction (Contracts invariant 9).

    Returns (new policy, previous version or None).
    """
    previous = db.execute(text("select max(version) from policies")).scalar()
    row = db.execute(
        text(
            "insert into policies (body, created_by) values (cast(:body as jsonb), :created_by) "
            f"returning {_COLUMNS}"
        ),
        {"body": json.dumps(body.model_dump(mode="json")), "created_by": created_by},
    ).mappings().one()
    policy = _to_policy(row)

    parameters = {
        "from_version": previous,
        "to_version": policy.version,
        "name": body.name,
        "preset": body.preset.value,
        "source": source,
        **(extra or {}),
    }
    db.execute(
        text(
            "insert into audit_log (id, actor, tool, parameters, reason, policy_version, dry_run) "
            "values (gen_random_uuid(), :actor, 'policy_change', cast(:parameters as jsonb), "
            ":reason, :policy_version, false)"
        ),
        {
            "actor": "system" if created_by == "system" else "human",
            "parameters": json.dumps(parameters),
            "reason": f"Policy version {policy.version} saved ({source})",
            "policy_version": policy.version,
        },
    )
    db.commit()
    return policy, previous


def get_current(db: Session) -> Policy:
    row = db.execute(
        text(f"select {_COLUMNS} from policies order by version desc limit 1")
    ).mappings().first()
    if row is None:  # first run: start from the default preset
        policy, _ = create_version(db, presets.preset_body(presets.DEFAULT_PRESET), "system", "seed")
        return policy
    return _to_policy(row)


def list_policies(db: Session) -> list[Policy]:
    get_current(db)  # makes sure the default exists
    rows = db.execute(text(f"select {_COLUMNS} from policies order by version desc")).mappings().all()
    return [_to_policy(r) for r in rows]


def get_version(db: Session, version: int) -> Policy:
    row = db.execute(
        text(f"select {_COLUMNS} from policies where version = :v"), {"v": version}
    ).mappings().first()
    if row is None:
        raise AppError(404, "policy_not_found", f"No policy with version {version}")
    return _to_policy(row)