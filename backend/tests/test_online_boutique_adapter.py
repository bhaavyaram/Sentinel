from pathlib import Path

from app.adapters.loader import parse_adapter

ADAPTER = Path(__file__).resolve().parents[2] / "adapters" / "online-boutique.yaml"


def test_online_boutique_adapter_parses():
    adapter = parse_adapter(ADAPTER.read_text(encoding="utf-8"))
    assert adapter.app == "online-boutique"
    assert len(adapter.services) == 11
    assert len(adapter.declared_dependencies) == 15


def test_redis_cart_is_stateful_critical_with_only_connection_failure():
    adapter = parse_adapter(ADAPTER.read_text(encoding="utf-8"))
    redis = next(s for s in adapter.services if s.name == "redis-cart")
    assert redis.type.value == "stateful"
    assert redis.critical is True
    assert [f.value for f in redis.faults] == ["connection_failure"]