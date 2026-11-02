"""Tests for catalog price, title and MCP response handling."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.schemas.requisicao import AgentItemSelection
from app.services.catalog_validation import (
    CatalogUnavailableError,
    InvalidCatalogPriceError,
    InvalidCatalogProductError,
    InvalidCatalogTitleError,
    McpCatalogClient,
    ProductNotFoundError,
    validate_and_price_items,
)
from app.services.pricing import decimal_from_catalog


def _selection(produto_id: int = 7, quantidade: int = 3) -> AgentItemSelection:
    return AgentItemSelection(produto_id=produto_id, titulo="Ignorado pelo backend", quantidade=quantidade)


def _success_payload(product: dict) -> dict:
    return {"status": "success", "product": product}


def _client_returning(payload: dict) -> MagicMock:
    client = MagicMock()
    client.detalhar_produto = AsyncMock(return_value=payload)
    return client


def test_quantity_above_max_is_rejected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _selection(quantidade=1001)


@pytest.mark.asyncio
async def test_price_valid() -> None:
    client = _client_returning(
        _success_payload({"id": 7, "title": "Laptop", "price": "999.99"})
    )
    items = await validate_and_price_items(selections=[_selection()], mcp_client=client)
    assert items[0].preco_unitario == Decimal("999.99")
    assert items[0].subtotal == Decimal("2999.97")
    assert items[0].titulo == "Laptop"


@pytest.mark.asyncio
async def test_records_backend_detalhar_success() -> None:
    from app.schemas.requisicao import FerramentaExecucao

    client = _client_returning(
        _success_payload({"id": 7, "title": "Laptop", "price": "999.99"})
    )
    execucoes: list[FerramentaExecucao] = []
    await validate_and_price_items(
        selections=[_selection()],
        mcp_client=client,
        execucoes=execucoes,
    )
    assert [item.model_dump() for item in execucoes] == [
        {"nome": "detalhar_produto", "origem": "backend", "status": "success"}
    ]


@pytest.mark.asyncio
async def test_records_backend_detalhar_payload_error() -> None:
    from app.schemas.requisicao import FerramentaExecucao

    client = _client_returning({"status": "error", "message": "timeout interno"})
    execucoes: list[FerramentaExecucao] = []
    with pytest.raises(CatalogUnavailableError):
        await validate_and_price_items(
            selections=[_selection()],
            mcp_client=client,
            execucoes=execucoes,
        )
    assert [item.model_dump() for item in execucoes] == [
        {"nome": "detalhar_produto", "origem": "backend", "status": "error"}
    ]


@pytest.mark.asyncio
async def test_records_backend_detalhar_not_found_as_success() -> None:
    from app.schemas.requisicao import FerramentaExecucao

    client = _client_returning({"status": "not_found"})
    execucoes: list[FerramentaExecucao] = []
    with pytest.raises(ProductNotFoundError):
        await validate_and_price_items(
            selections=[_selection()],
            mcp_client=client,
            execucoes=execucoes,
        )
    assert [item.model_dump() for item in execucoes] == [
        {"nome": "detalhar_produto", "origem": "backend", "status": "success"}
    ]


@pytest.mark.asyncio
async def test_price_missing() -> None:
    client = _client_returning(_success_payload({"id": 7, "title": "Laptop"}))
    with pytest.raises(InvalidCatalogPriceError):
        await validate_and_price_items(selections=[_selection()], mcp_client=client)


@pytest.mark.asyncio
async def test_price_null() -> None:
    client = _client_returning(_success_payload({"id": 7, "title": "Laptop", "price": None}))
    with pytest.raises(InvalidCatalogPriceError):
        await validate_and_price_items(selections=[_selection()], mcp_client=client)


@pytest.mark.asyncio
async def test_price_negative() -> None:
    client = _client_returning(_success_payload({"id": 7, "title": "Laptop", "price": "-10.00"}))
    with pytest.raises(InvalidCatalogPriceError):
        await validate_and_price_items(selections=[_selection()], mcp_client=client)


@pytest.mark.asyncio
async def test_price_invalid_format() -> None:
    client = _client_returning(_success_payload({"id": 7, "title": "Laptop", "price": "dez reais"}))
    with pytest.raises(InvalidCatalogPriceError):
        await validate_and_price_items(selections=[_selection()], mcp_client=client)


@pytest.mark.asyncio
async def test_price_zero_is_allowed() -> None:
    client = _client_returning(_success_payload({"id": 7, "title": "Brinde", "price": "0"}))
    items = await validate_and_price_items(selections=[_selection(quantidade=1)], mcp_client=client)
    assert items[0].preco_unitario == Decimal("0.00")
    assert items[0].subtotal == Decimal("0.00")


@pytest.mark.asyncio
async def test_title_missing() -> None:
    client = _client_returning(_success_payload({"id": 7, "price": "10.00"}))
    with pytest.raises(InvalidCatalogTitleError):
        await validate_and_price_items(selections=[_selection()], mcp_client=client)


@pytest.mark.asyncio
async def test_title_null() -> None:
    client = _client_returning(_success_payload({"id": 7, "title": None, "price": "10.00"}))
    with pytest.raises(InvalidCatalogTitleError):
        await validate_and_price_items(selections=[_selection()], mcp_client=client)


@pytest.mark.asyncio
async def test_title_empty() -> None:
    client = _client_returning(_success_payload({"id": 7, "title": "   ", "price": "10.00"}))
    with pytest.raises(InvalidCatalogTitleError):
        await validate_and_price_items(selections=[_selection()], mcp_client=client)


@pytest.mark.asyncio
async def test_title_does_not_fallback_to_agent() -> None:
    client = _client_returning(_success_payload({"id": 7, "title": "", "price": "10.00"}))
    with pytest.raises(InvalidCatalogTitleError):
        await validate_and_price_items(selections=[_selection()], mcp_client=client)


@pytest.mark.asyncio
async def test_catalog_id_mismatch() -> None:
    client = _client_returning(_success_payload({"id": 99, "title": "Outro", "price": "10.00"}))
    with pytest.raises(InvalidCatalogProductError):
        await validate_and_price_items(selections=[_selection()], mcp_client=client)


@pytest.mark.asyncio
async def test_product_not_found_is_not_unavailable() -> None:
    client = _client_returning({"status": "not_found", "product": None})
    with pytest.raises(ProductNotFoundError):
        await validate_and_price_items(selections=[_selection()], mcp_client=client)


@pytest.mark.asyncio
async def test_catalog_error_status_is_unavailable() -> None:
    client = _client_returning({"status": "error", "message": "timeout interno"})
    with pytest.raises(CatalogUnavailableError):
        await validate_and_price_items(selections=[_selection()], mcp_client=client)


def test_decimal_from_catalog_valid_and_zero() -> None:
    assert decimal_from_catalog("10.50") == Decimal("10.50")
    assert decimal_from_catalog(0) == Decimal("0.00")


def test_decimal_from_catalog_rejects_empty_and_float() -> None:
    with pytest.raises(ValueError):
        decimal_from_catalog("")
    with pytest.raises(ValueError):
        decimal_from_catalog(None)
    with pytest.raises(ValueError):
        decimal_from_catalog(1.99)


class _FakeSession:
    def __init__(self, result: object | Exception) -> None:
        self._result = result

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def initialize(self) -> None:
        return None

    async def call_tool(self, *_args: object, **_kwargs: object) -> object:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _patch_mcp(result: object | Exception):
    session = _FakeSession(result)

    def fake_streamable(*_args: object, **_kwargs: object):
        cm = AsyncMock()
        cm.__aenter__.return_value = (MagicMock(), MagicMock())
        cm.__aexit__.return_value = None
        return cm

    return (
        patch("app.services.catalog_validation.streamable_http_client", side_effect=fake_streamable),
        patch("app.services.catalog_validation.ClientSession", return_value=session),
    )


@pytest.mark.asyncio
async def test_mcp_is_error_without_not_found() -> None:
    result = SimpleNamespace(
        is_error=True,
        isError=True,
        structured_content={"status": "error", "message": "boom"},
        content=[],
    )
    stream_patch, session_patch = _patch_mcp(result)
    with stream_patch, session_patch:
        client = McpCatalogClient("http://localhost:8080/mcp")
        with pytest.raises(CatalogUnavailableError, match="Catálogo indisponível"):
            await client.detalhar_produto(7)


@pytest.mark.asyncio
async def test_mcp_empty_content() -> None:
    result = SimpleNamespace(is_error=False, isError=False, structured_content=None, content=[])
    stream_patch, session_patch = _patch_mcp(result)
    with stream_patch, session_patch:
        client = McpCatalogClient("http://localhost:8080/mcp")
        with pytest.raises(CatalogUnavailableError):
            await client.detalhar_produto(7)


@pytest.mark.asyncio
async def test_mcp_invalid_json() -> None:
    result = SimpleNamespace(
        is_error=False,
        isError=False,
        structured_content=None,
        content=[SimpleNamespace(text="não é json")],
    )
    stream_patch, session_patch = _patch_mcp(result)
    with stream_patch, session_patch:
        client = McpCatalogClient("http://localhost:8080/mcp")
        with pytest.raises(CatalogUnavailableError):
            await client.detalhar_produto(7)


@pytest.mark.asyncio
async def test_mcp_unexpected_structure() -> None:
    result = SimpleNamespace(
        is_error=False,
        isError=False,
        structured_content=None,
        content=[SimpleNamespace(text='["lista"]')],
    )
    stream_patch, session_patch = _patch_mcp(result)
    with stream_patch, session_patch:
        client = McpCatalogClient("http://localhost:8080/mcp")
        with pytest.raises(CatalogUnavailableError):
            await client.detalhar_produto(7)


@pytest.mark.asyncio
async def test_mcp_timeout() -> None:
    stream_patch, session_patch = _patch_mcp(httpx.TimeoutException("timed out"))
    with stream_patch, session_patch:
        client = McpCatalogClient("http://localhost:8080/mcp", timeout_seconds=1.0)
        with pytest.raises(CatalogUnavailableError, match="Catálogo indisponível"):
            await client.detalhar_produto(7)


@pytest.mark.asyncio
async def test_mcp_connection_failure() -> None:
    stream_patch, session_patch = _patch_mcp(httpx.ConnectError("connection failed"))
    with stream_patch, session_patch:
        client = McpCatalogClient("http://localhost:8080/mcp")
        with pytest.raises(CatalogUnavailableError, match="Catálogo indisponível"):
            await client.detalhar_produto(7)


@pytest.mark.asyncio
async def test_mcp_structured_not_found_preserved() -> None:
    result = SimpleNamespace(
        is_error=False,
        isError=False,
        structured_content={"status": "not_found", "product": None},
        content=[],
    )
    stream_patch, session_patch = _patch_mcp(result)
    with stream_patch, session_patch:
        client = McpCatalogClient("http://localhost:8080/mcp")
        payload = await client.detalhar_produto(999)
    with pytest.raises(ProductNotFoundError):
        await validate_and_price_items(
            selections=[_selection(produto_id=999, quantidade=1)],
            mcp_client=SimpleNamespace(detalhar_produto=AsyncMock(return_value=payload)),
        )


def test_catalog_client_uses_public_mcp_http_api() -> None:
    import inspect

    import app.services.catalog_validation as module

    source = inspect.getsource(module)
    assert "import httpx2" not in source
    assert "from mcp.shared._httpx_utils" not in source
    assert "from mcp.client.streamable_http import create_mcp_http_client" in source


def test_http_timeout_is_portable_tuple() -> None:
    from app.services.catalog_validation import _http_timeout

    assert _http_timeout(10.0, 120.0) == (10.0, 120.0, 10.0, 10.0)
