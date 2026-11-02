"""Extract executed MCP tool names from ADK function responses."""

from __future__ import annotations

from typing import Any

INTERNAL_ADK_TOOL_NAMES = frozenset({"set_model_response"})


def collect_executed_tool_names(function_responses: list[Any]) -> list[str]:
    """Return unique tool names in first-execution order, excluding ADK internals."""
    names: list[str] = []
    seen: set[str] = set()
    for function_response in function_responses:
        name = getattr(function_response, "name", None)
        if not isinstance(name, str):
            continue
        cleaned = name.strip()
        if not cleaned or cleaned in INTERNAL_ADK_TOOL_NAMES or cleaned in seen:
            continue
        seen.add(cleaned)
        names.append(cleaned)
    return names
