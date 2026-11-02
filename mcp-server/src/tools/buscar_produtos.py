"""buscar_produtos MCP tool handler."""

from __future__ import annotations

from typing import Any

from dummyjson_client import (
    DummyJsonClient,
    DummyJsonConnectionError,
    DummyJsonError,
    DummyJsonHttpError,
    DummyJsonInvalidResponseError,
    DummyJsonTimeoutError,
    map_product_fields,
)

MAX_TERM_LENGTH = 200


def _validate_termo(termo: str) -> str | None:
    if termo is None:
        return "O termo de busca é obrigatório."
    cleaned = termo.strip()
    if not cleaned:
        return "O termo de busca não pode ser vazio."
    if len(cleaned) > MAX_TERM_LENGTH:
        return f"O termo de busca deve ter no máximo {MAX_TERM_LENGTH} caracteres."
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
        "detail": exc.message,
        "products": [],
        "total": 0,
    }


async def execute_buscar_produtos(termo: str, client: DummyJsonClient) -> dict[str, Any]:
    """
    Search products by term in DummyJSON.

    Empty results are a successful catalog response (no matches), not an infrastructure failure.
    """
    validation_error = _validate_termo(termo)
    if validation_error:
        return {
            "status": "error",
            "error_kind": "invalid_input",
            "message": validation_error,
            "products": [],
            "total": 0,
        }

    cleaned_term = termo.strip()

    try:
        payload = await client.search_products(cleaned_term)
    except (DummyJsonTimeoutError, DummyJsonConnectionError, DummyJsonHttpError, DummyJsonInvalidResponseError) as exc:
        return _catalog_unavailable_response(exc)

    products_raw = payload.get("products")
    if products_raw is None:
        return {
            "status": "error",
            "error_kind": "invalid_response",
            "message": "Resposta inesperada do catálogo.",
            "products": [],
            "total": 0,
        }

    if not isinstance(products_raw, list):
        return {
            "status": "error",
            "error_kind": "invalid_response",
            "message": "Resposta inesperada do catálogo.",
            "products": [],
            "total": 0,
        }

    products = [map_product_fields(item) for item in products_raw if isinstance(item, dict)]

    total_raw = payload.get("total", len(products))
    try:
        total = int(total_raw)
    except (TypeError, ValueError):
        total = len(products)

    if not products:
        return {
            "status": "empty",
            "termo": cleaned_term,
            "message": "Nenhum produto encontrado para o termo informado.",
            "products": [],
            "total": 0,
        }

    return {
        "status": "success",
        "termo": cleaned_term,
        "products": products,
        "total": total,
    }
