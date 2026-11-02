"""detalhar_produto MCP tool handler."""

from __future__ import annotations

from typing import Any

from dummyjson_client import (
    DummyJsonClient,
    DummyJsonConnectionError,
    DummyJsonError,
    DummyJsonHttpError,
    DummyJsonInvalidResponseError,
    DummyJsonNotFoundError,
    DummyJsonTimeoutError,
    map_product_fields,
)


def _validate_product_id(product_id: int) -> str | None:
    if isinstance(product_id, bool):
        return "O identificador do produto deve ser um número inteiro positivo."
    if not isinstance(product_id, int):
        return "O identificador do produto deve ser um número inteiro positivo."
    if product_id < 1:
        return "O identificador do produto deve ser um número inteiro positivo."
    return None


def _catalog_unavailable_response(exc: DummyJsonError) -> dict[str, Any]:
    kind_map = {
        "timeout": "timeout",
        "connection": "connection",
        "http_error": "http_error",
        "invalid_response": "invalid_response",
    }
    return {
        "status": "error",
        "error_kind": kind_map.get(exc.kind, "catalog_unavailable"),
        "message": (
            "O catálogo está indisponível no momento. "
            "Tente novamente em instantes."
        ),
        "product": None,
    }


async def execute_detalhar_produto(product_id: int, client: DummyJsonClient) -> dict[str, Any]:
    """Fetch a single product by id from DummyJSON."""
    validation_error = _validate_product_id(product_id)
    if validation_error:
        return {
            "status": "error",
            "error_kind": "invalid_input",
            "message": validation_error,
            "product": None,
        }

    try:
        payload = await client.get_product(product_id)
    except DummyJsonNotFoundError:
        return {
            "status": "not_found",
            "error_kind": "product_not_found",
            "message": f"Produto com id {product_id} não existe no catálogo.",
            "product_id": product_id,
            "product": None,
        }
    except (DummyJsonTimeoutError, DummyJsonConnectionError, DummyJsonHttpError, DummyJsonInvalidResponseError) as exc:
        return _catalog_unavailable_response(exc)

    try:
        product = map_product_fields(payload)
    except DummyJsonInvalidResponseError as exc:
        return _catalog_unavailable_response(exc)

    return {
        "status": "success",
        "product_id": product_id,
        "product": product,
    }
