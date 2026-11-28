import pytest
from docker.errors import DockerException

from app.tools.base import ToolError
from app.tools.containers import find_container


class FakeContainers:
    def __init__(self, found):
        self.found = found
        self.calls = []

    def list(self, all, filters):  # noqa: A002 - mirrors the Docker SDK signature
        self.calls.append({"all": all, "filters": filters})
        return self.found


class FakeClient:
    def __init__(self, found):
        self.containers = FakeContainers(found)


def test_lookup_uses_service_and_project_labels(monkeypatch):
    client = FakeClient(["the-container"])
    monkeypatch.setattr("app.tools.containers.docker.from_env", lambda: client)

    assert find_container("cartservice", "online-boutique") == "the-container"
    call = client.containers.calls[0]
    assert call["all"] is True
    assert call["filters"] == {
        "label": [
            "com.docker.compose.service=cartservice",
            "com.docker.compose.project=online-boutique",
        ]
    }


def test_lookup_without_project_uses_only_service_label(monkeypatch):
    client = FakeClient(["the-container"])
    monkeypatch.setattr("app.tools.containers.docker.from_env", lambda: client)

    find_container("cartservice")
    assert client.containers.calls[0]["filters"] == {
        "label": ["com.docker.compose.service=cartservice"]
    }


def test_missing_container_raises_tool_error(monkeypatch):
    monkeypatch.setattr("app.tools.containers.docker.from_env", lambda: FakeClient([]))
    with pytest.raises(ToolError):
        find_container("cartservice")


def test_docker_unreachable_raises_tool_error(monkeypatch):
    def boom():
        raise DockerException("pipe closed")

    monkeypatch.setattr("app.tools.containers.docker.from_env", boom)
    with pytest.raises(ToolError):
        find_container("cartservice")