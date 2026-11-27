"""Parsing of imported policy JSON."""

from pydantic import ValidationError

from app.errors import AppError
from app.schemas import PolicyBody

# Assigned by the server on every save. An exported file contains them; an import ignores them.
SERVER_FIELDS = ("version", "created_by", "created_at")


def parse_policy_body(data: object) -> PolicyBody:
    if not isinstance(data, dict):
        raise AppError(422, "invalid_policy", "A policy must be a JSON object")
    cleaned = {key: value for key, value in data.items() if key not in SERVER_FIELDS}
    try:
        return PolicyBody.model_validate(cleaned)
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        raise AppError(422, "invalid_policy", details)