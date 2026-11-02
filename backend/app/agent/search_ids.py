"""Extract product IDs from ADK function_response events of buscar_produtos."""

from __future__ import annotations

import json
from typing import Any, NamedTuple


class BuscarProdutosParse(NamedTuple):
    """Parsed payload of a single buscar_produtos tool response."""

    product_ids: frozenset[int]
    recognized: bool
    catalog_failed: bool


class SearchObservation(NamedTuple):
    """Union of buscar_produtos results observed in one agent run."""

    product_ids: frozenset[int]
    observed: bool
    catalog_failed: bool


_INFRA_ERROR_KINDS = frozenset(
    {
        "timeout",
        "connection",
        "http_error",
        "invalid_response",
        "catalog_unavailable",
    }
)


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


def _is_infra_error(payload: dict[str, Any]) -> bool:
    """True when buscar_produtos reports catalog/infrastructure failure.

    ``error_kind=invalid_input`` is a client validation problem, not DummyJSON down.
    A bare ``status=error`` is treated as infrastructure failure (fail closed).
    """
    kind = payload.get("error_kind")
    if kind == "invalid_input":
        return False
    if kind in _INFRA_ERROR_KINDS:
        return True
    return True


def parse_buscar_produtos_response(response: object) -> BuscarProdutosParse:
    """Parse a buscar_produtos tool payload.

    ``recognized`` is True when the payload looks like a buscar_produtos result
    (success, empty or error), even if the product list is empty.
    ``catalog_failed`` is True only for infrastructure/catalog unavailability.
    """
    for payload in _payload_candidates(response):
        status = payload.get("status")
        if status == "error":
            return BuscarProdutosParse(
                product_ids=frozenset(),
                recognized=True,
                catalog_failed=_is_infra_error(payload),
            )
        if status in {"success", "empty"}:
            return BuscarProdutosParse(
                product_ids=_ids_from_products(payload.get("products")),
                recognized=True,
                catalog_failed=False,
            )
        if "products" in payload:
            return BuscarProdutosParse(
                product_ids=_ids_from_products(payload.get("products")),
                recognized=True,
                catalog_failed=False,
            )
    return BuscarProdutosParse(product_ids=frozenset(), recognized=False, catalog_failed=False)


def collect_search_ids(function_responses: list[Any]) -> SearchObservation:
    """Union IDs from buscar_produtos responses in the current agent run.

    Catalog unavailability wins when every observed search is an infrastructure
    error. A later successful or empty search means the catalog responded, so
    IDs from that response remain valid.
    """
    ids: set[int] = set()
    observed = False
    saw_catalog_up = False
    saw_infra_error = False
    for function_response in function_responses:
        name = getattr(function_response, "name", None)
        if name != "buscar_produtos":
            continue
        observed = True
        parsed = parse_buscar_produtos_response(getattr(function_response, "response", None))
        if parsed.catalog_failed:
            saw_infra_error = True
            continue
        if parsed.recognized:
            saw_catalog_up = True
            ids.update(parsed.product_ids)
    return SearchObservation(
        product_ids=frozenset(ids),
        observed=observed,
        catalog_failed=saw_infra_error and not saw_catalog_up,
    )
