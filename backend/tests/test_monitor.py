from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents import emit as emit_module
from app.agents.catalog import ServiceInfo
from app.agents.incidents import FakeIncidents
from app.agents.monitor import Monitor
from app.agents.settings import agent_settings
from app.schemas.enums import Actor, EventType, ServiceHealth

APP_ID = uuid4()
CART = ServiceInfo("cartservice", "stateless", False)
REDIS = ServiceInfo("redis-cart", "stateful", True)
HEALTHY = ServiceHealth.healthy


@pytest.fixture
def published(monkeypatch):
    calls = []

    def fake_publish(application_id, type, actor, payload, incident_id=None, policy_version=None):  # noqa: A002
        calls.append({"type": type, "actor": actor, "payload": payload})
        return SimpleNamespace(event_id=uuid4())

    monkeypatch.setattr(emit_module, "publish", fake_publish)
    monkeypatch.setattr(agent_settings, "real_incidents", False)
    return calls


def make_monitor(states, on_incident=None):
    return Monitor(FakeIncidents(), get_health=lambda app_id, name: states[name], on_incident=on_incident)


def test_healthy_services_open_nothing(published):
    monitor = make_monitor({"cartservice": HEALTHY, "redis-cart": HEALTHY})
    assert monitor.check(APP_ID, [CART, REDIS]) == []
    assert published == []


def test_down_service_opens_one_incident_with_first_event(published):
    monitor = make_monitor({"cartservice": ServiceHealth.down, "redis-cart": HEALTHY})
    opened = monitor.check(APP_ID, [CART, REDIS])
    assert len(opened) == 1
    kinds = [event["type"] for event in published]
    assert kinds == [EventType.incident_opened, EventType.agent_step]
    assert published[0]["payload"]["severity"] == "high"
    assert published[1]["actor"] == Actor.monitor


def test_critical_service_down_is_critical(published):
    monitor = make_monitor({"cartservice": HEALTHY, "redis-cart": ServiceHealth.down})
    monitor.check(APP_ID, [CART, REDIS])
    assert published[0]["payload"]["severity"] == "critical"


def test_degraded_service_is_medium(published):
    monitor = make_monitor({"cartservice": ServiceHealth.degraded, "redis-cart": HEALTHY})
    monitor.check(APP_ID, [CART, REDIS])
    assert published[0]["payload"]["severity"] == "medium"


def test_no_duplicate_incident_while_still_failing(published):
    monitor = make_monitor({"cartservice": ServiceHealth.down, "redis-cart": HEALTHY})
    assert len(monitor.check(APP_ID, [CART])) == 1
    assert monitor.check(APP_ID, [CART]) == []


def test_recovery_then_new_failure_opens_a_new_incident(published):
    states = {"cartservice": ServiceHealth.down}
    monitor = make_monitor(states)
    assert len(monitor.check(APP_ID, [CART])) == 1
    states["cartservice"] = HEALTHY
    monitor.check(APP_ID, [CART])
    states["cartservice"] = ServiceHealth.down
    assert len(monitor.check(APP_ID, [CART])) == 1


def test_unknown_does_not_forget_an_active_incident(published):
    states = {"cartservice": ServiceHealth.down}
    monitor = make_monitor(states)
    monitor.check(APP_ID, [CART])
    states["cartservice"] = ServiceHealth.unknown
    monitor.check(APP_ID, [CART])
    states["cartservice"] = ServiceHealth.down
    assert monitor.check(APP_ID, [CART]) == []


def test_failing_workflow_does_not_stop_the_monitor(published):
    seen = []

    def on_incident(application_id, incident_id, service):
        seen.append(service)
        raise RuntimeError("workflow exploded")

    monitor = make_monitor(
        {"cartservice": ServiceHealth.down, "redis-cart": ServiceHealth.down}, on_incident
    )
    assert len(monitor.check(APP_ID, [CART, REDIS])) == 2
    assert seen == ["cartservice", "redis-cart"]


def test_sweep_once_uses_the_loaders(published):
    monitor = make_monitor({"cartservice": ServiceHealth.down, "redis-cart": HEALTHY})
    monitor.sweep_once(
        list_apps=lambda: [APP_ID],
        load=lambda app_id: {"cartservice": CART, "redis-cart": REDIS},
    )
    assert any(event["type"] == EventType.incident_opened for event in published)