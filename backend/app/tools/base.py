"""Tool registry and the untrusted-result wrapper (Contracts 4.2 and section 6)."""

from collections.abc import Callable
from typing import Any, Literal

from app.schemas import GatewayRequest
from app.schemas.base import ContractModel


class ToolError(Exception):
    """A tool could not do its job (Docker unreachable, container missing, bad input)."""


class ToolResult(ContractModel):
    """What the gateway returns for a tool call: { data, untrusted: true }.

    Log lines, trace attributes and error messages inside `data` are untrusted content.
    They must never be placed in an instruction position of any prompt (Contracts section 6).
    """

    data: dict[str, Any]
    untrusted: Literal[True] = True


# A handler receives the gateway request and returns the tool's `data` dictionary.
ToolHandler = Callable[[GatewayRequest], dict[str, Any]]

_registry: dict[str, ToolHandler] = {}


def register_tool(tool: str, handler: ToolHandler) -> None:
    if tool in _registry:
        raise ValueError(f"tool '{tool}' is already registered")
    _registry[tool] = handler


def get_tool(tool: str) -> ToolHandler:
    try:
        return _registry[tool]
    except KeyError:
        raise ToolError(f"unknown tool '{tool}'") from None


def clear_registry() -> None:
    """Used by tests so one test's registrations do not leak into another."""
    _registry.clear()


def wrap(data: dict[str, Any]) -> ToolResult:
    """Mark a handler's output as untrusted data."""
    return ToolResult(data=data)