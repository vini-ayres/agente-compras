"""Tests for detalhar_produto tool handler."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from config import Settings
from dummyjson_client import (
    DummyJsonClient,
    DummyJsonHttpError,
    DummyJsonInvalidResponseError,
    DummyJsonNotFoundError,
    DummyJsonTimeoutError,
    map_product_fields,
)
from tools.detalhar_produto import execute_detalhar_produto


@pytest.fixture
def client(settings: Settings) -> DummyJsonClient:
    return DummyJsonClient(settings)


def test_map_product_fields_rejects_missing_price() -> None:
    with pytest.raises(DummyJsonInvalidResponseError):
        map_product_fields({"id": 1, "title": "X"})


def test_map_product_fields_keeps_numeric_price() -> None:
    mapped = map_product_fields(
        {
            "id": 7,
            "title": "Apple MacBook Pro",
            "description": "MacBook Pro",
            "category": "laptops",
            "price": 1749.99,
            "stock": 25,
            "rating": 4.77,
        }
    )
    assert mapped["price"] == "1749.99"
    assert mapped["title"] == "Apple MacBook Pro"


@pytest.mark.asyncio
async def test_detalhar_produto_success(client: DummyJsonClient) -> None:
    client.get_product = AsyncMock(
        return_value={
            "id": 7,
            "title": "Apple MacBook Pro",
            "description": "MacBook Pro",
            "category": "laptops",
            "price": 1749.99,
            "stock": 25,
            "rating": 4.77,
        }
    )

    result = await execute_detalhar_produto(7, client)

    assert result["status"] == "success"
    assert result["product_id"] == 7
    assert result["product"]["title"] == "Apple MacBook Pro"
    assert result["product"]["price"] == "1749.99"


@pytest.mark.asyncio
async def test_detalhar_produto_not_found(client: DummyJsonClient) -> None:
    client.get_product = AsyncMock(side_effect=DummyJsonNotFoundError(999_999))

    result = await execute_detalhar_produto(999_999, client)

    assert result["status"] == "not_found"
    assert result["error_kind"] == "product_not_found"
    assert result["product"] is None


@pytest.mark.asyncio
async def test_detalhar_produto_timeout(client: DummyJsonClient) -> None:
    client.get_product = AsyncMock(side_effect=DummyJsonTimeoutError())

    result = await execute_detalhar_produto(1, client)

    assert result["status"] == "error"
    assert result["error_kind"] == "timeout"
    assert result["product"] is None


@pytest.mark.asyncio
async def test_detalhar_produto_http_error(client: DummyJsonClient) -> None:
    client.get_product = AsyncMock(side_effect=DummyJsonHttpError(500))

    result = await execute_detalhar_produto(1, client)

    assert result["status"] == "error"
    assert result["error_kind"] == "http_error"


@pytest.mark.asyncio
async def test_detalhar_produto_invalid_id(client: DummyJsonClient) -> None:
    result = await execute_detalhar_produto(0, client)

    assert result["status"] == "error"
    assert result["error_kind"] == "invalid_input"


@pytest.mark.asyncio
async def test_detalhar_produto_missing_price_is_error(client: DummyJsonClient) -> None:
    client.get_product = AsyncMock(
        return_value={
            "id": 7,
            "title": "Apple MacBook Pro",
            "description": "MacBook Pro",
            "category": "laptops",
            "stock": 25,
            "rating": 4.77,
        }
    )

    result = await execute_detalhar_produto(7, client)

    assert result["status"] == "error"
    assert result["error_kind"] == "invalid_response"
    assert result["product"] is None
    assert "detail" not in result


@pytest.mark.asyncio
async def test_dummyjson_client_get_product_404(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url=settings.dummyjson_base_url) as http_client:
        client = DummyJsonClient(settings, client=http_client)
        with pytest.raises(DummyJsonNotFoundError):
            await client.get_product(42)
