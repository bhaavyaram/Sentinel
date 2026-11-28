from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents import emit as emit_module
from app.agents.incidents import FakeIncidents
from app.agents.settings import agent_settings
from app.schemas.enums import Actor, EventType, IncidentStatus, Severity

APP_ID = uuid4()


@pytest.fixture
def published(monkeypatch):
    calls = []

    def fake_publish(application_id, type, actor, payload, incident_id=None, policy_version=None):  # noqa: A002
        calls.append({"type": type, "actor": actor, "payload": payload, "incident_id": incident_id})
        return SimpleNamespace(event_id=uuid4())

    monkeypatch.setattr(emit_module, "publish", fake_publish)
    monkeypatch.setattr(agent_settings, "real_incidents", False)
    return calls


def test_open_incident_publishes_incident_opened(published):
    incidents = FakeIncidents()
    incident_id = incidents.open_incident(APP_ID, Severity.high, "cartservice")

    event = published[0]
    assert event["type"] == EventType.incident_opened
    assert event["actor"] == Actor.monitor
    assert event["payload"]["severity"] == "high"
    assert event["payload"]["trigger_service"] == "cartservice"
    assert event["payload"]["incident_id"] == str(incident_id)
    assert event["incident_id"] is None  # fake incidents: the id travels in the payload
    assert incidents.status_of(incident_id) == IncidentStatus.open


def test_set_status_publishes_only_on_change(published):
    incidents = FakeIncidents()
    incident_id = incidents.open_incident(APP_ID, Severity.high, "cartservice")
    incidents.set_status(incident_id, IncidentStatus.investigating)
    incidents.set_status(incident_id, IncidentStatus.investigating)

    changes = [e for e in published if e["type"] == EventType.incident_status_changed]
    assert len(changes) == 1
    assert changes[0]["payload"]["from"] == "open"
    assert changes[0]["payload"]["to"] == "investigating"


def test_close_incident_needs_a_final_status(published):
    incidents = FakeIncidents()
    incident_id = incidents.open_incident(APP_ID, Severity.low, "cartservice")
    with pytest.raises(ValueError):
        incidents.close_incident(incident_id, IncidentStatus.recovering, None)
    incidents.close_incident(incident_id, IncidentStatus.resolved, "crash")
    assert incidents.status_of(incident_id) == IncidentStatus.resolved


def test_real_incidents_put_the_id_in_the_column(published, monkeypatch):
    monkeypatch.setattr(agent_settings, "real_incidents", True)
    incidents = FakeIncidents()
    incident_id = incidents.open_incident(APP_ID, Severity.low, "cartservice")
    assert published[0]["incident_id"] == incident_id
    assert "incident_id" not in published[0]["payload"]