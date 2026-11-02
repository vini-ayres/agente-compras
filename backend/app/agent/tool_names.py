"""Extract executed MCP tool calls from ADK function responses."""

from __future__ import annotations

import json
from typing import Any, Literal

from app.schemas.requisicao import FerramentaExecucao

INTERNAL_ADK_TOOL_NAMES = frozenset({"set_model_response"})
ToolStatus = Literal["success", "error"]


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _payload_candidates(response: object) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if not isinstance(response, dict):
        return candidates
    candidates.append(response)

    result = response.get("result")
    if isinstance(result, dict):
        candidates.append(result)
    elif isinstance(result, str) and result.strip():
        parsed = _parse_json_object(result)
        if parsed is not None:
            candidates.append(parsed)

    structured = response.get("structuredContent") or response.get("structured_content")
    if isinstance(structured, dict):
        candidates.append(structured)

    content = response.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                parsed = _parse_json_object(text)
                if parsed is not None:
                    candidates.append(parsed)
    return candidates


def _status_from_payloads(payloads: list[dict[str, Any]]) -> ToolStatus | None:
    for payload in payloads:
        status = payload.get("status")
        if status == "error":
            return "error"
        if status in {"success", "empty", "not_found"}:
            return "success"
        if "products" in payload or "product" in payload:
            return "success"
    return None


def _execution_status(function_response: object) -> ToolStatus:
    if bool(getattr(function_response, "is_error", False) or getattr(function_response, "isError", False)):
        payloads = _payload_candidates(getattr(function_response, "response", None))
        for payload in payloads:
            if payload.get("status") == "not_found":
                return "success"
        return "error"
    parsed = _status_from_payloads(_payload_candidates(getattr(function_response, "response", None)))
    return parsed if parsed is not None else "success"


def collect_executed_tools(function_responses: list[Any]) -> list[FerramentaExecucao]:
    """Return each agent MCP tool execution in first-seen order, excluding ADK internals."""
    executions: list[FerramentaExecucao] = []
    for function_response in function_responses:
        name = getattr(function_response, "name", None)
        if not isinstance(name, str):
            continue
        cleaned = name.strip()
        if not cleaned or cleaned in INTERNAL_ADK_TOOL_NAMES:
            continue
        executions.append(
            FerramentaExecucao(
                nome=cleaned,
                origem="agent",
                status=_execution_status(function_response),
            )
        )
    return executions
