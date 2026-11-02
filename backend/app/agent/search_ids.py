"""Extract product IDs from ADK function_response events of buscar_produtos."""

from __future__ import annotations

import json
from typing import Any


def _as_int_id(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _ids_from_products(products: object) -> frozenset[int]:
    if not isinstance(products, list):
        return frozenset()
    found: set[int] = set()
    for item in products:
        if not isinstance(item, dict):
            continue
        product_id = _as_int_id(item.get("id"))
        if product_id is not None:
            found.add(product_id)
    return frozenset(found)


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


def parse_buscar_produtos_response(response: object) -> tuple[frozenset[int], bool]:
    """Return (ids, recognized).

    recognized is True when the payload looks like a buscar_produtos result
    (success, empty or error), even if the product list is empty.
    """
    for payload in _payload_candidates(response):
        status = payload.get("status")
        if status in {"success", "empty", "error"}:
            return _ids_from_products(payload.get("products")), True
        if "products" in payload:
            return _ids_from_products(payload.get("products")), True
    return frozenset(), False


def collect_search_ids(function_responses: list[Any]) -> tuple[frozenset[int], bool]:
    """Union IDs from buscar_produtos responses in the current agent run."""
    ids: set[int] = set()
    observed = False
    for function_response in function_responses:
        name = getattr(function_response, "name", None)
        if name != "buscar_produtos":
            continue
        observed = True
        chunk, recognized = parse_buscar_produtos_response(
            getattr(function_response, "response", None)
        )
        if recognized:
            ids.update(chunk)
    return frozenset(ids), observed
