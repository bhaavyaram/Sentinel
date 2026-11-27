import uuid

from app.chaos import expiry
from app.errors import AppError
from app.schemas import Actor


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _setup(monkeypatch, experiment_id, clear):
    monkeypatch.setattr(expiry, "SessionLocal", FakeSession)
    monkeypatch.setattr(expiry, "_retry_after", {})
    monkeypatch.setattr(expiry, "_find_expired_ids", lambda: [experiment_id])
    monkeypatch.setattr(expiry.runner, "clear_experiment", clear)


def test_expired_experiment_is_cleared_as_system(monkeypatch):
    experiment_id = uuid.uuid4()
    calls: list[tuple] = []

    def clear(db, eid, caller, reason):
        calls.append((eid, caller, reason))

    _setup(monkeypatch, experiment_id, clear)
    expiry.clear_expired()

    assert calls == [(experiment_id, Actor.system, "duration_expired")]


def test_failed_clear_is_not_retried_immediately(monkeypatch):
    experiment_id = uuid.uuid4()
    attempts: list[int] = []

    def clear(db, eid, caller, reason):
        attempts.append(1)
        raise AppError(502, "chaos_failed", "Docker is down")

    _setup(monkeypatch, experiment_id, clear)
    expiry.clear_expired()
    expiry.clear_expired()

    assert len(attempts) == 1


def test_already_cleared_experiment_is_ignored(monkeypatch):
    experiment_id = uuid.uuid4()

    def clear(db, eid, caller, reason):
        raise AppError(409, "experiment_already_cleared", "done")

    _setup(monkeypatch, experiment_id, clear)
    expiry.clear_expired()

    assert experiment_id not in expiry._retry_after