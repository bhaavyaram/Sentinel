import uuid

from app.monitoring import health, state
from app.monitoring.state import HealthTracker
from app.schemas import EventType, ServiceHealth

APP = uuid.uuid4()


def test_classify_running_with_passing_probe_is_healthy():
    assert health.classify("running", True) == ServiceHealth.healthy


def test_classify_running_without_probe_is_healthy():
    assert health.classify("running", None) == ServiceHealth.healthy


def test_classify_running_with_failed_probe_is_degraded():
    assert health.classify("running", False) == ServiceHealth.degraded


def test_classify_stopped_container_is_down():
    for status in ("exited", "dead", "created", "paused"):
        assert health.classify(status, None) == ServiceHealth.down


def test_classify_restarting_is_degraded():
    assert health.classify("restarting", None) == ServiceHealth.degraded


def test_classify_missing_container_is_unknown():
    assert health.classify(None, None) == ServiceHealth.unknown


def test_tracker_first_healthy_observation_is_silent():
    tracker = HealthTracker()
    assert tracker.observe(APP, "cart", ServiceHealth.healthy) is None
    assert tracker.get(APP, "cart") == ServiceHealth.healthy


def test_tracker_first_down_observation_is_reported():
    tracker = HealthTracker()
    assert tracker.observe(APP, "cart", ServiceHealth.down) == (ServiceHealth.unknown, ServiceHealth.down)


def test_tracker_healthy_to_down_is_reported_once():
    tracker = HealthTracker()
    tracker.observe(APP, "cart", ServiceHealth.healthy)
    assert tracker.observe(APP, "cart", ServiceHealth.down) == (ServiceHealth.healthy, ServiceHealth.down)
    assert tracker.observe(APP, "cart", ServiceHealth.down) is None


def test_tracker_needs_two_degraded_observations():
    tracker = HealthTracker()
    tracker.observe(APP, "cart", ServiceHealth.healthy)
    assert tracker.observe(APP, "cart", ServiceHealth.degraded) is None
    assert tracker.observe(APP, "cart", ServiceHealth.degraded) == (
        ServiceHealth.healthy,
        ServiceHealth.degraded,
    )


def test_tracker_healthy_observation_resets_the_degraded_count():
    tracker = HealthTracker()
    tracker.observe(APP, "cart", ServiceHealth.healthy)
    tracker.observe(APP, "cart", ServiceHealth.degraded)
    tracker.observe(APP, "cart", ServiceHealth.healthy)
    assert tracker.observe(APP, "cart", ServiceHealth.degraded) is None


def test_sweep_publishes_one_event_when_a_container_dies(monkeypatch):
    adapter = {
        "compose_project": "shop",
        "services": [{"name": "cartservice", "container": "cartservice", "health": "tcp://localhost:7070"}],
    }
    published: list[tuple] = []

    monkeypatch.setattr(state, "tracker", HealthTracker())
    monkeypatch.setattr(health, "_load_applications", lambda: [(APP, adapter)])
    monkeypatch.setattr(health.probes, "probe", lambda address, timeout=1.0: True)
    monkeypatch.setattr(health.events, "publish", lambda *args, **kwargs: published.append(args))

    monkeypatch.setattr(health, "_container_states", lambda: {("shop", "cartservice"): "running"})
    health.sweep_once()
    assert published == []  # starting healthy is not news

    monkeypatch.setattr(health, "_container_states", lambda: {("shop", "cartservice"): "exited"})
    health.sweep_once()
    health.sweep_once()  # a second sweep must not repeat the event

    assert len(published) == 1
    _, event_type, _, payload = published[0]
    assert event_type == EventType.service_health_changed
    assert payload == {"service": "cartservice", "from": "healthy", "to": "down"}



def test_stopped_container_is_reported_without_probing(monkeypatch):
    adapter = {
        "compose_project": "shop",
        "services": [{"name": "cartservice", "container": "cartservice", "health": "tcp://localhost:7070"}],
    }
    published: list[tuple] = []

    def probe_must_not_run(address, timeout=1.0):
        raise AssertionError("a stopped container must not be probed")

    monkeypatch.setattr(state, "tracker", HealthTracker())
    monkeypatch.setattr(health, "_load_applications", lambda: [(APP, adapter)])
    monkeypatch.setattr(health, "_container_states", lambda: {("shop", "cartservice"): "exited"})
    monkeypatch.setattr(health.probes, "probe", probe_must_not_run)
    monkeypatch.setattr(health.events, "publish", lambda *args, **kwargs: published.append(args))

    health.sweep_once()

    assert len(published) == 1
    assert published[0][3] == {"service": "cartservice", "from": "unknown", "to": "down"}
