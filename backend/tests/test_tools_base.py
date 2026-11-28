import pytest
from pydantic import ValidationError

from app.tools.base import ToolError, ToolResult, clear_registry, get_tool, register_tool, wrap


@pytest.fixture(autouse=True)
def _empty_registry():
    clear_registry()
    yield
    clear_registry()


def test_register_and_get_tool():
    handler = lambda request: {"ok": True}  # noqa: E731
    register_tool("restart_service", handler)
    assert get_tool("restart_service") is handler


def test_duplicate_registration_is_rejected():
    register_tool("restart_service", lambda request: {})
    with pytest.raises(ValueError):
        register_tool("restart_service", lambda request: {})


def test_unknown_tool_raises():
    with pytest.raises(ToolError):
        get_tool("does_not_exist")


def test_wrap_marks_data_untrusted():
    result = wrap({"lines": []})
    assert result.untrusted is True
    assert result.data == {"lines": []}


def test_tool_result_cannot_claim_to_be_trusted():
    with pytest.raises(ValidationError):
        ToolResult(data={}, untrusted=False)