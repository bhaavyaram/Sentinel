"""Clears experiments whose duration_s has passed."""

import logging
import time
import uuid

from sqlalchemy import text

from app.chaos import runner
from app.db import SessionLocal
from app.errors import AppError
from app.schemas import Actor

log = logging.getLogger(__name__)

RETRY_DELAY_S = 30.0  # after a failed clear, wait before trying that experiment again
_retry_after: dict[uuid.UUID, float] = {}

_EXPIRED_SQL = (
    "select id from experiments "
    "where ended_at is null "
    "and (parameters->>'duration_s') is not null "
    "and started_at + cast(parameters->>'duration_s' as integer) * interval '1 second' <= now() "
    "order by started_at"
)


def _find_expired_ids() -> list[uuid.UUID]:
    with SessionLocal() as db:
        return [row[0] for row in db.execute(text(_EXPIRED_SQL)).all()]


def clear_expired() -> None:
    for experiment_id in _find_expired_ids():
        if _retry_after.get(experiment_id, 0.0) > time.monotonic():
            continue
        with SessionLocal() as db:
            try:
                runner.clear_experiment(
                    db, experiment_id, caller=Actor.system, reason=runner.REASON_DURATION_EXPIRED
                )
            except AppError as exc:
                if exc.code == "experiment_already_cleared":
                    continue  # a person cleared it a moment ago
                log.error("could not auto-clear experiment %s: %s", experiment_id, exc.message)
                _retry_after[experiment_id] = time.monotonic() + RETRY_DELAY_S
            else:
                _retry_after.pop(experiment_id, None)