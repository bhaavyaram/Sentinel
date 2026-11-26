from pathlib import Path

import pytest
from pydantic import ValidationError

from app.adapters.loader import parse_adapter
from app.schemas import AdapterFile

ADAPTER = Path(__file__).resolve().parents[2] / "adapters" / "online-boutique.yaml"


def minimal(health: str) -> dict:
    return {
        "app": "demo",
        "compose_project": "demo",
        "services": [
            {
                "name": "a",
                "container": "a",
                "type": "stateless",
                "health": health,
                "faults": ["crash"],
            }
        ],
    }


def test_compose_project_is_accepted():
    adapter = AdapterFile.model_validate(minimal("tcp://localhost:22001"))
    assert adapter.compose_project == "demo"


def test_http_url_health_is_accepted():
    adapter = AdapterFile.model_validate(minimal("http://localhost:22000/_healthz"))
    assert adapter.services[0].health == "http://localhost:22000/_healthz"


def test_unknown_health_scheme_is_rejected():
    with pytest.raises(ValidationError):
        AdapterFile.model_validate(minimal("ftp://localhost:21"))


def test_online_boutique_health_is_host_reachable():
    adapter = parse_adapter(ADAPTER.read_text(encoding="utf-8"))
    assert adapter.compose_project == "online-boutique"
    for svc in adapter.services:
        assert svc.health is not None
        assert svc.health.startswith(("tcp://localhost:", "http://localhost:")), svc.name