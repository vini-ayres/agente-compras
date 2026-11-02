"""Tests for buscar_produtos tool handler."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from config import Settings
from dummyjson_client import (
    DummyJsonClient,
    DummyJsonConnectionError,
    DummyJsonHttpError,
    DummyJsonTimeoutError,
)
from tools.buscar_produtos import execute_buscar_produtos


@pytest.fixture
def client(settings: Settings) -> DummyJsonClient:
    return DummyJsonClient(settings)


@pytest.mark.asyncio
async def test_buscar_produtos_success(client: DummyJsonClient) -> None:
    client.search_products = AsyncMock(
        return_value={
            "products": [
                {
                    "id": 1,
                    "title": "iPhone 9",
                    "description": "An apple mobile",
                    "category": "smartphones",
                    "price": 549,
                    "stock": 94,
                    "rating": 4.69,
                }
            ],
            "total": 1,
        }
    )

    result = await execute_buscar_produtos("phone", client)

    assert result["status"] == "success"
    assert result["termo"] == "phone"
    assert result["total"] == 1
    assert len(result["products"]) == 1
    product = result["products"][0]
    assert product["id"] == 1
    assert product["title"] == "iPhone 9"
    assert product["price"] == "549"
    assert product["stock"] == 94
    assert product["rating"] == 4.69


@pytest.mark.asyncio
async def test_buscar_produtos_empty(client: DummyJsonClient) -> None:
    client.search_products = AsyncMock(return_value={"products": [], "total": 0})

    result = await execute_buscar_produtos("xyzinexistente", client)

    assert result["status"] == "empty"
    assert result["products"] == []
    assert result["total"] == 0
    assert "Nenhum produto encontrado" in result["message"]


@pytest.mark.asyncio
async def test_buscar_produtos_timeout(client: DummyJsonClient) -> None:
    client.search_products = AsyncMock(side_effect=DummyJsonTimeoutError())

    result = await execute_buscar_produtos("laptop", client)

    assert result["status"] == "error"
    assert result["error_kind"] == "timeout"
    assert result["products"] == []


@pytest.mark.asyncio
async def test_buscar_produtos_http_error(client: DummyJsonClient) -> None:
    client.search_products = AsyncMock(side_effect=DummyJsonHttpError(503))

    result = await execute_buscar_produtos("laptop", client)

    assert result["status"] == "error"
    assert result["error_kind"] == "http_error"


@pytest.mark.asyncio
async def test_buscar_produtos_invalid_term(client: DummyJsonClient) -> None:
    result = await execute_buscar_produtos("   ", client)

    assert result["status"] == "error"
    assert result["error_kind"] == "invalid_input"


def _raise_timeout(_request: httpx.Request) -> httpx.Response:
    raise httpx.TimeoutException("timed out")


def _raise_connect_error(_request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection failed")


@pytest.mark.asyncio
async def test_dummyjson_client_search_timeout(settings: Settings) -> None:
    transport = httpx.MockTransport(_raise_timeout)
    async with httpx.AsyncClient(transport=transport, base_url=settings.dummyjson_base_url) as http_client:
        client = DummyJsonClient(settings, client=http_client)
        with pytest.raises(DummyJsonTimeoutError):
            await client.search_products("laptop")


@pytest.mark.asyncio
async def test_dummyjson_client_search_connection_error(settings: Settings) -> None:
    transport = httpx.MockTransport(_raise_connect_error)
    async with httpx.AsyncClient(transport=transport, base_url=settings.dummyjson_base_url) as http_client:
        client = DummyJsonClient(settings, client=http_client)
        with pytest.raises(DummyJsonConnectionError):
            await client.search_products("laptop")
