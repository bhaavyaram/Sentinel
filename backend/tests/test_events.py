import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import events
from app.event_hub import EventHub
from app.schemas import Actor, EventType, SentinelEvent

EXPERIMENT_PAYLOAD = {"experiment_id": "e1", "service": "cartservice", "fault_type": "crash"}


def test_missing_payload_keys_are_rejected():
    with pytest.raises(events.EventPublishError):
        events.publish(uuid.uuid4(), EventType.experiment_started, Actor.human, {"service": "x"})


def test_publish_stores_first_then_pushes(monkeypatch):
    calls: list[str] = []

    def fake_insert(application_id, incident_id, actor, event_type, payload, policy_version):
        calls.append("store")
        event = SentinelEvent(
            event_id=uuid.uuid4(),
            ts=datetime.now(timezone.utc),
            application_id=application_id,
            incident_id=incident_id,
            actor=actor,
            type=event_type,
            payload=payload,
            policy_version=policy_version,
        )
        return 7, event

    monkeypatch.setattr(events.events_repo, "insert_event", fake_insert)
    monkeypatch.setattr(events.hub, "push", lambda app_id, seq, event: calls.append("push"))

    event = events.publish(uuid.uuid4(), EventType.experiment_started, Actor.human, EXPERIMENT_PAYLOAD)

    assert calls == ["store", "push"]
    assert event.type == EventType.experiment_started


def test_store_failure_raises_and_pushes_nothing(monkeypatch):
    pushed: list[int] = []

    def boom(*args, **kwargs):
        raise SQLAlchemyError("database is down")

    monkeypatch.setattr(events.events_repo, "insert_event", boom)
    monkeypatch.setattr(events.hub, "push", lambda *args: pushed.append(1))

    with pytest.raises(events.EventPublishError):
        events.publish(uuid.uuid4(), EventType.experiment_started, Actor.human, EXPERIMENT_PAYLOAD)
    assert pushed == []


def test_hub_delivers_only_to_subscribers_of_the_same_application():
    async def scenario():
        hub = EventHub()
        app_a, app_b = uuid.uuid4(), uuid.uuid4()
        sub_a = hub.subscribe(app_a)
        sub_b = hub.subscribe(app_b)

        hub.push(app_a, 1, "event-a")  # a plain string is enough for this test
        seq, event = await asyncio.wait_for(sub_a.queue.get(), timeout=1)

        assert (seq, event) == (1, "event-a")
        assert sub_b.queue.empty()

    asyncio.run(scenario())


def test_hub_stops_delivering_after_unsubscribe():
    async def scenario():
        hub = EventHub()
        app_id = uuid.uuid4()
        sub = hub.subscribe(app_id)
        hub.unsubscribe(sub)

        hub.push(app_id, 1, "event")
        await asyncio.sleep(0.05)

        assert sub.queue.empty()

    asyncio.run(scenario())