from pathlib import Path

import pytest

from app.adapters.loader import AdapterError, parse_adapter

SAMPLE = Path(__file__).resolve().parents[2] / "adapters" / "sample-shop.yaml"


def test_sample_adapter_parses():
    adapter = parse_adapter(SAMPLE.read_text(encoding="utf-8"))
    assert adapter.app == "sample-shop"
    assert len(adapter.services) == 4
    assert len(adapter.declared_dependencies) == 4


def test_invalid_yaml_is_rejected():
    with pytest.raises(AdapterError, match="Invalid YAML"):
        parse_adapter("a: [unclosed")


def test_top_level_must_be_a_mapping():
    with pytest.raises(AdapterError, match="mapping"):
        parse_adapter("- a\n- b")


def test_unknown_fault_error_names_the_location():
    text = SAMPLE.read_text(encoding="utf-8").replace("[crash, latency]", "[meteor_strike]", 1)
    with pytest.raises(AdapterError, match=r"services\.0\.faults\.0"):
        parse_adapter(text)


def test_missing_required_field_is_reported():
    with pytest.raises(AdapterError, match="app"):
        parse_adapter("version: 1\nservices: []\n")