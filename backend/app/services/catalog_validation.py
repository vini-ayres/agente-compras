"""Authoritative catalog validation via MCP detalhar_produto."""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from app.schemas.requisicao import MAX_ITEM_QUANTITY, AgentItemSelection, ValidatedLineItem
from app.services.pricing import decimal_from_catalog, line_subtotal

logger = logging.getLogger(__name__)

_GENERIC_CATALOG_UNAVAILABLE = "Catálogo indisponível."
_TIMEOUT_TYPE_NAMES = frozenset({"TimeoutException"})
_CONNECTION_TYPE_NAMES = frozenset({"ConnectError", "RequestError"})


class CatalogValidationError(Exception):
    """Base error for catalog validation."""

    kind: str = "validation"


class CatalogUnavailableError(CatalogValidationError):
    kind = "catalog_unavailable"


class ProductNotFoundError(CatalogValidationError):
    kind = "product_not_found"


class InvalidCatalogPriceError(CatalogValidationError):
    kind = "invalid_price"


class InvalidCatalogTitleError(CatalogValidationError):
    kind = "invalid_title"


class InvalidCatalogProductError(CatalogValidationError):
    kind = "invalid_product"


class ProductNotInSearchError(CatalogValidationError):
    kind = "product_not_in_search"


def _is_timeout_error(exc: BaseException) -> bool:
    return isinstance(exc, (TimeoutError, httpx.TimeoutException)) or type(exc).__name__ in _TIMEOUT_TYPE_NAMES


def _is_connection_error(exc: BaseException) -> bool:
    return (
        isinstance(exc, (ConnectionError, OSError, httpx.ConnectError, httpx.RequestError))
        or type(exc).__name__ in _CONNECTION_TYPE_NAMES
    )


def _http_timeout(connect_seconds: float, read_seconds: float) -> tuple[float, float, float, float]:
    """Portable timeout for MCP's HTTP client (httpx or httpx2).

    MCP SDK 2.x builds the client with httpx2. Passing ``httpx.Timeout`` raises
    TypeError; a ``(connect, read, write, pool)`` tuple is accepted by both majors.
    """
    return (connect_seconds, read_seconds, connect_seconds, connect_seconds)


def _is_tool_error(result: Any) -> bool:
    """Installed MCP SDK exposes ``is_error``; wire name is ``isError``."""
    return bool(getattr(result, "is_error", False) or getattr(result, "isError", False))


def _payload_from_tool_result(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured

    content = getattr(result, "content", None) or []
    if not content:
        raise CatalogUnavailableError(_GENERIC_CATALOG_UNAVAILABLE)

    text = getattr(content[0], "text", None)
    if not text or not str(text).strip():
        raise CatalogUnavailableError(_GENERIC_CATALOG_UNAVAILABLE)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CatalogUnavailableError(_GENERIC_CATALOG_UNAVAILABLE) from exc

    if not isinstance(payload, dict):
        raise CatalogUnavailableError(_GENERIC_CATALOG_UNAVAILABLE)
    return payload


def _catalog_price(product: dict[str, Any]) -> Decimal:
    if "price" not in product:
        raise InvalidCatalogPriceError("Preço ausente no catálogo.")
    try:
        return decimal_from_catalog(product["price"])
    except ValueError as exc:
        raise InvalidCatalogPriceError(str(exc)) from exc


def _catalog_title(product: dict[str, Any]) -> str:
    if "title" not in product:
        raise InvalidCatalogTitleError("Título ausente no catálogo.")
    title = product["title"]
    if title is None:
        raise InvalidCatalogTitleError("Título ausente no catálogo.")
    if not isinstance(title, str):
        raise InvalidCatalogTitleError("Título inválido no catálogo.")
    cleaned = title.strip()
    if not cleaned:
        raise InvalidCatalogTitleError("Título ausente no catálogo.")
    return cleaned


def _catalog_id(product: dict[str, Any], requested_id: int) -> int:
    if "id" not in product or product["id"] is None:
        raise InvalidCatalogProductError("Identificador de produto inconsistente.")
    try:
        catalog_id = int(product["id"])
    except (TypeError, ValueError) as exc:
        raise InvalidCatalogProductError("Identificador de produto inconsistente.") from exc
    if catalog_id != requested_id:
        raise InvalidCatalogProductError("Identificador de produto inconsistente.")
    return catalog_id


class McpCatalogClient:
    """Minimal MCP client for backend integrity checks (detalhar_produto only)."""

    def __init__(
        self,
        mcp_server_url: str,
        *,
        timeout_seconds: float = 10.0,
        sse_read_timeout_seconds: float = 120.0,
    ) -> None:
        self._url = mcp_server_url
        self._timeout_seconds = timeout_seconds
        self._sse_read_timeout_seconds = sse_read_timeout_seconds

    async def detalhar_produto(self, product_id: int) -> dict[str, Any]:
        try:
            http_client = create_mcp_http_client(
                timeout=_http_timeout(self._timeout_seconds, self._sse_read_timeout_seconds)
            )
            async with http_client:
                async with streamable_http_client(self._url, http_client=http_client) as streams:
                    read, write = streams[0], streams[1]
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool("detalhar_produto", {"id": product_id})
        except Exception as exc:  # noqa: BLE001 - mapped to domain error
            if isinstance(exc, CatalogValidationError):
                raise
            if _is_timeout_error(exc):
                logger.warning("Timeout ao consultar MCP detalhar_produto")
                raise CatalogUnavailableError(_GENERIC_CATALOG_UNAVAILABLE) from exc
            if _is_connection_error(exc):
                logger.warning("Falha de conexão ao consultar MCP detalhar_produto")
                raise CatalogUnavailableError(_GENERIC_CATALOG_UNAVAILABLE) from exc
            logger.warning("Falha ao consultar MCP detalhar_produto: %s", type(exc).__name__)
            raise CatalogUnavailableError(_GENERIC_CATALOG_UNAVAILABLE) from exc

        try:
            payload = _payload_from_tool_result(result)
        except CatalogUnavailableError:
            raise

        if _is_tool_error(result) and payload.get("status") != "not_found":
            raise CatalogUnavailableError(_GENERIC_CATALOG_UNAVAILABLE)

        return payload


def _map_tool_payload(payload: dict[str, Any], product_id: int) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise CatalogUnavailableError(_GENERIC_CATALOG_UNAVAILABLE)

    status = payload.get("status")
    if status == "not_found":
        raise ProductNotFoundError(f"Produto {product_id} não encontrado no catálogo.")
    if status == "error":
        raise CatalogUnavailableError(_GENERIC_CATALOG_UNAVAILABLE)
    if status != "success":
        raise CatalogUnavailableError(_GENERIC_CATALOG_UNAVAILABLE)

    product = payload.get("product")
    if not isinstance(product, dict):
        raise CatalogUnavailableError(_GENERIC_CATALOG_UNAVAILABLE)
    return product


async def validate_and_price_items(
    *,
    selections: list[AgentItemSelection],
    mcp_client: McpCatalogClient,
) -> list[ValidatedLineItem]:
    """Re-fetch each product from MCP and recalculate monetary values."""
    validated: list[ValidatedLineItem] = []
    for selection in selections:
        if selection.quantidade <= 0 or selection.quantidade > MAX_ITEM_QUANTITY:
            raise InvalidCatalogProductError("Quantidade deve ser um inteiro positivo até 1000.")

        payload = await mcp_client.detalhar_produto(selection.produto_id)
        product = _map_tool_payload(payload, selection.produto_id)
        produto_id = _catalog_id(product, selection.produto_id)
        unit_price = _catalog_price(product)
        titulo = _catalog_title(product)
        subtotal = line_subtotal(selection.quantidade, unit_price)

        validated.append(
            ValidatedLineItem(
                produto_id=produto_id,
                titulo=titulo,
                quantidade=selection.quantidade,
                preco_unitario=unit_price,
                subtotal=subtotal,
            )
        )
    return validated
