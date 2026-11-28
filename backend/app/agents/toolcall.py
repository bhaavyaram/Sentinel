"""How agents call Diagnostics tools until the real gateway exists.

Contracts 4.1 says every tool call goes through gateway.submit. The placeholder gateway
blocks everything except chaos, and the return shape is still open (Q3/Q4), so for now the
Diagnostics tools (read-only, low risk) are called directly through this one function.
When Backend Step 8b ships, only this file changes.
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from app.tools import diagnostics
from app.tools.base import ToolError

CallTool = Callable[..., dict[str, Any]]


def direct_diagnostics(application_id: UUID) -> CallTool:
    handlers = {
        "query_logs": diagnostics.query_logs,
        "query_metrics": diagnostics.query_metrics,
        "get_traces": diagnostics.get_traces,
        "get_service_status": diagnostics.get_service_status,
        "get_dependencies": diagnostics.get_dependencies,
    }

    def call(tool: str, **args: Any) -> dict[str, Any]:
        handler = handlers.get(tool)
        if handler is None:
            raise ToolError(f"unknown diagnostics tool '{tool}'")
        return handler(application_id, **args)

    return call